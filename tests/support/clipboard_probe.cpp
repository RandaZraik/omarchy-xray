// Test-only foreign MIME offer: even probing its text format counts as a read.
// An editable Qt TextField must trigger this probe; guarded fields must not.
#include <QClipboard>
#include <QGuiApplication>
#include <QMimeData>
#include <QQmlExtensionPlugin>
#include <qqml.h>
#include <memory>

class ClipboardOffer final : public QMimeData {
public:
    explicit ClipboardOffer(std::shared_ptr<int> reads) : reads(std::move(reads)) {}
    bool hasFormat(const QString &) const override { ++*reads; return true; }
    QStringList formats() const override { ++*reads; return {"text/plain"}; }
protected:
    QVariant retrieveData(const QString &, QMetaType) const override {
        ++*reads;
        return QString("foreign clipboard");
    }
private:
    std::shared_ptr<int> reads;
};

class ClipboardProbe : public QObject {
    Q_OBJECT
    Q_PROPERTY(int reads READ reads)
public:
    explicit ClipboardProbe(QObject *parent = nullptr) : QObject(parent) {}
    int reads() const { return *counter; }
    Q_INVOKABLE void offer() {
        *counter = 0;
        QGuiApplication::clipboard()->setMimeData(new ClipboardOffer(counter));
    }
private:
    std::shared_ptr<int> counter = std::make_shared<int>(0);
};

class ClipboardProbePlugin : public QQmlExtensionPlugin {
    Q_OBJECT
    Q_PLUGIN_METADATA(IID QQmlExtensionInterface_iid)
public:
    void registerTypes(const char *uri) override {
        qmlRegisterType<ClipboardProbe>(uri, 1, 0, "ClipboardProbe");
    }
};

#include "clipboard_probe.moc"
