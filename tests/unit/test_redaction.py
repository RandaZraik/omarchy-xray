from pathlib import Path
import unittest

from xray.evidence.redaction import (
    redact_argument,
    redact_command,
    redact_snapshot,
    redact_text,
)


class RedactionTests(unittest.TestCase):
    def test_malformed_urls_and_private_key_blocks_fail_closed(self) -> None:
        malformed = "http://user:pass@example.com:bad/path?token=SECRET"
        self.assertEqual(redact_argument(malformed), "http://<redacted-url>")
        self.assertNotIn(
            "user:pass",
            redact_text(f"request failed for {malformed}"),
        )
        for label in ("PRIVATE KEY", "RSA PRIVATE KEY", "PGP PRIVATE KEY BLOCK"):
            with self.subTest(label=label):
                block = f"-----BEGIN {label}-----\nSECRET"
                self.assertEqual(
                    redact_text(block),
                    "<redacted private key>",
                )

    def test_missing_command_is_empty_instead_of_literal_none(self) -> None:
        self.assertEqual(redact_command(None), [])
        self.assertEqual(redact_command([]), [])

    def test_redacts_secret_flags_urls_home_and_addresses(self) -> None:
        snapshot = {
            "context": {
                "workingDirectory": "/home/example/work",
                "command": [
                    "demo",
                    "--token",
                    "secret",
                    "--api-key=value",
                    "https://user:pass@example.com/a?q=secret",
                ],
            },
            "connections": [
                {"localAddress": "192.168.1.4", "remoteAddress": "8.8.8.8"}
            ],
            "container": {
                "networks": [{"address": "10.0.0.2", "gateway": "10.0.0.1"}],
                "ports": [{"hostAddress": "192.168.1.4"}],
            },
        }
        redacted = redact_snapshot(snapshot, Path("/home/example"))
        self.assertEqual(redacted["context"]["workingDirectory"], "~/work")
        self.assertEqual(redacted["context"]["command"][2], "<redacted>")
        self.assertEqual(redacted["context"]["command"][3], "--api-key=<redacted>")
        self.assertEqual(redacted["context"]["command"][4], "https://example.com/a")
        self.assertEqual(redacted["connections"][0]["localAddress"], "<private-ip>")
        self.assertEqual(redacted["connections"][0]["remoteAddress"], "<remote-ip>")
        self.assertEqual(
            redacted["container"]["networks"][0]["address"], "<private-ip>"
        )
        self.assertEqual(
            redacted["container"]["networks"][0]["gateway"], "<private-ip>"
        )
        self.assertEqual(
            redacted["container"]["ports"][0]["hostAddress"], "<private-ip>"
        )

    def test_malformed_url_still_redacts_embedded_secrets(self) -> None:
        value = "https://example.com:not-a-port/path?token=leak-me"
        redacted = redact_argument(value)
        self.assertNotIn("leak-me", redacted)
        self.assertEqual(redacted, "https://<redacted-url>")

    def test_generic_passphrases_and_account_keys_are_redacted(self) -> None:
        redacted = redact_snapshot(
            {
                "passphrase": "phrase-secret",
                "nested": {"accountKey": "account-secret"},
                "command": ["demo", "--passphrase", "command-secret"],
            }
        )

        self.assertEqual(redacted["passphrase"], "<redacted>")
        self.assertEqual(redacted["nested"]["accountKey"], "<redacted>")
        self.assertEqual(redacted["command"][-1], "<redacted>")

    def test_environment_style_secret_assignments_never_cross_the_boundary(
        self,
    ) -> None:
        values = (
            "MY_API_KEY=supersecret",
            "AWS_SECRET_ACCESS_KEY=abc123",
            "DATABASE_URL=postgres://alice:hunter2@example.test/app",
            "CONNECTION_STRING=postgres://alice:hunter2@example.test/app",
            "PGPASSWORD=hunter2",
            "MYSQL_PWD=hunter2",
        )

        for value in values:
            with self.subTest(value=value):
                redacted = redact_argument(value)
                self.assertTrue(redacted.endswith("=<redacted>"), redacted)
                self.assertNotIn(value.split("=", 1)[1], redacted)

        message = (
            "AWS_SECRET_ACCESS_KEY=abc123 DATABASE_URL=postgres://alice:hunter2@db/app"
        )
        self.assertNotIn("abc123", redact_text(message))
        self.assertNotIn("hunter2", redact_text(message))

    def test_embedded_credential_urls_are_sanitized_inside_log_prose(self) -> None:
        message = (
            "failed connecting to postgres://alice:hunter2@db.example/app; "
            "retry=https://user:pass@[2001:db8::1]:8443/path?token=secret."
        )

        redacted = redact_text(message)

        self.assertNotIn("alice", redacted)
        self.assertNotIn("hunter2", redacted)
        self.assertNotIn("user:pass", redacted)
        self.assertNotIn("token=secret", redacted)
        self.assertIn("postgres://db.example/app", redacted)
        self.assertIn("https://[2001:db8::1]:8443/path", redacted)

    def test_webhook_and_bot_tokens_in_url_paths_are_redacted(self) -> None:
        cases = (
            (
                "https://discord.com/api/webhooks/123456/VERY_SECRET_TOKEN",
                "VERY_SECRET_TOKEN",
            ),
            (
                "https://hooks.slack.com/services/T000/B000/VERYSECRET",
                "VERYSECRET",
            ),
            (
                "https://api.telegram.org/bot123456:SECRET/sendMessage",
                "123456:SECRET",
            ),
        )

        for value, secret in cases:
            with self.subTest(value=value):
                redacted = redact_text("failed request to " + value)
                self.assertNotIn(secret, redacted)
                self.assertIn("<redacted>", redacted)

    def test_unrecognized_assignment_still_sanitizes_a_structural_url(self) -> None:
        redacted = redact_argument(
            "CUSTOM_ENDPOINT=postgres://alice:hunter2@db.example/app?sslkey=secret"
        )

        self.assertEqual(redacted, "CUSTOM_ENDPOINT=postgres://db.example/app")

    def test_container_entrypoint_uses_sequential_argument_redaction(self) -> None:
        redacted = redact_snapshot(
            {
                "context": {
                    "container": {
                        "entrypoint": ["app", "--password", "entry-secret"],
                        "command": ["worker", "--token", "command-secret"],
                    }
                }
            }
        )
        container = redacted["context"]["container"]
        self.assertEqual(container["entrypoint"], ["app", "--password", "<redacted>"])
        self.assertEqual(container["command"], ["worker", "--token", "<redacted>"])

    def test_redacts_secrets_embedded_in_logs_headers_and_tokens(self) -> None:
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.signature"
        message = (
            f"login password=hunter2; Authorization: Bearer live-secret\nsession={jwt}"
        )
        redacted = redact_text(message)
        self.assertNotIn("hunter2", redacted)
        self.assertNotIn("live-secret", redacted)
        self.assertNotIn(jwt, redacted)
        self.assertIn("password=<redacted>", redacted)

    def test_redacts_json_shaped_log_secrets(self) -> None:
        message = (
            '{"password":"hunter2","token":"abc","Authorization":"Bearer live-secret"}'
        )

        redacted = redact_text(message)

        self.assertNotIn("hunter2", redacted)
        self.assertNotIn('"abc"', redacted)
        self.assertNotIn("live-secret", redacted)

    def test_redacts_standard_command_specific_credential_flags(self) -> None:
        cases = (
            (["curl", "-u", "alice:hunter2"], "alice:hunter2"),
            (["curl", "--user=alice:hunter2"], "alice:hunter2"),
            (["curl", "--proxy-user", "alice:hunter2"], "alice:hunter2"),
            (["curl", "--oauth2-bearer", "hunter2"], "hunter2"),
            (["curl", "--oauth2-bearer=hunter2"], "hunter2"),
            (["curl", "--pass", "hunter2"], "hunter2"),
            (["mysql", "-phunter2"], "hunter2"),
            (["mysql", "--password", "hunter2"], "hunter2"),
            (["redis-cli", "-a", "hunter2"], "hunter2"),
            (["redis-cli", "--pass=hunter2"], "hunter2"),
            (["docker", "login", "-phunter2", "registry.example"], "hunter2"),
            (["docker", "login", "--password", "hunter2"], "hunter2"),
            (
                ["docker", "--config", "/tmp/docker", "login", "-phunter2"],
                "hunter2",
            ),
            (
                ["docker", "--context", "prod", "login", "-p", "hunter2"],
                "hunter2",
            ),
            (["sshpass", "-phunter2", "ssh", "host"], "hunter2"),
            (["sshpass", "-p", "hunter2", "ssh", "host"], "hunter2"),
            (["java", "-Dpassword=hunter2", "Example"], "hunter2"),
            (["java", "-Ddb.password=hunter2", "Example"], "hunter2"),
            (
                ["java", "-Djavax.net.ssl.keyStorePassword=hunter2", "Example"],
                "hunter2",
            ),
            (["java", "-Dhttp.proxyPassword=hunter2", "Example"], "hunter2"),
            (["gpg", "--passphrase", "hunter2", "file.gpg"], "hunter2"),
            (["openssl", "rsa", "-passin", "pass:hunter2"], "hunter2"),
            (["openssl", "rsa", "-passout=pass:hunter2"], "hunter2"),
        )

        for command, secret in cases:
            with self.subTest(command=command):
                redacted = redact_command(command)
                joined = " ".join(redacted)
                self.assertNotIn(secret, joined)
                self.assertIn("<redacted>", joined)

        nested = redact_snapshot(
            {"context": {"keyStorePassword": "hunter2", "safe": "visible"}}
        )
        self.assertEqual(nested["context"]["keyStorePassword"], "<redacted>")
        self.assertEqual(nested["context"]["safe"], "visible")


if __name__ == "__main__":
    unittest.main()
