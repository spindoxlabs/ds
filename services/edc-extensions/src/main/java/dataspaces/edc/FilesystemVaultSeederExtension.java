package dataspaces.edc;

import org.eclipse.edc.runtime.metamodel.annotation.Extension;
import org.eclipse.edc.runtime.metamodel.annotation.Inject;
import org.eclipse.edc.spi.security.Vault;
import org.eclipse.edc.spi.system.ServiceExtension;
import org.eclipse.edc.spi.system.ServiceExtensionContext;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

@Extension("Dataspaces filesystem vault seeder")
public class FilesystemVaultSeederExtension implements ServiceExtension {

    @Inject
    private Vault vault;

    @Override
    public void initialize(ServiceExtensionContext context) {
        var vaultFile = context.getSetting("edc.vault.fs.file", null);
        if (vaultFile == null || vaultFile.isBlank()) {
            return;
        }

        var path = Path.of(vaultFile);
        if (!Files.exists(path)) {
            context.getMonitor().warning("Vault seed file not found: %s".formatted(path));
            return;
        }

        var properties = new Properties();
        try (InputStream stream = Files.newInputStream(path)) {
            properties.load(stream);
        } catch (IOException e) {
            throw new IllegalStateException("Failed to read vault seed file " + path, e);
        }

        properties.forEach((key, value) -> {
            var secretName = String.valueOf(key);
            var secretValue = String.valueOf(value);
            var result = vault.storeSecret(secretName, secretValue);
            if (result.failed()) {
                throw new IllegalStateException("Failed to store vault secret " + secretName);
            }
        });
        context.getMonitor().info("Loaded %d secrets from %s".formatted(properties.size(), path));
    }
}
