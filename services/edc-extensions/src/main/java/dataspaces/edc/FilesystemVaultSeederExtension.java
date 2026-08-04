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

/**
 * Seeds EDC's vault from a properties file.
 *
 * <p>The only {@link Vault} implementation on this runtime's classpath is EDC's
 * boot-default {@code InMemoryVault}: neither {@code vault-filesystem} nor
 * {@code vault-hashicorp} is packaged. So this extension is not one vault
 * backend among several — it is <b>the only thing that puts anything in the
 * vault</b>, and an unseeded vault resolves no alias at all. Both
 * {@code edc.transfer.proxy.token.signer.privatekey.alias} (the EDR signing key)
 * and {@code edc.iam.sts.oauth.client.secret.alias} (the STS credential) go
 * through it, so the failure is every signature and every DSP call, reported as
 * a missing secret rather than as a missing file.
 *
 * <h2>Why the setting is {@code ds.}, not {@code edc.}</h2>
 *
 * <p>It used to be {@code edc.vault.fs.file} — <b>the key EDC's own
 * {@code vault-filesystem} module reads</b>. Nothing collides today, because that
 * module is not on the classpath; the collision is latent and would be silent.
 * Add {@code vault-filesystem} to the BOM and two extensions read one key and
 * both claim the vault, with extension load order deciding which seed survives.
 *
 * <p>The key is now {@code ds.vault.seed.file}, in this unit's own namespace
 * alongside {@code ds.connector.internal.*} and
 * {@code ds.access.scope.cache.ttl.seconds}. The old key is still read, and
 * warns — dropping it outright would have started the connector with an empty
 * vault on any deployment that had not been updated, which is precisely the
 * silent failure this rename exists to prevent.
 */
@Extension("Dataspaces filesystem vault seeder")
public class FilesystemVaultSeederExtension implements ServiceExtension {

    static final String SEED_FILE = "ds.vault.seed.file";

    /** Superseded by {@link #SEED_FILE}; read for one release, with a warning. */
    static final String LEGACY_SEED_FILE = "edc.vault.fs.file";

    @Inject
    private Vault vault;

    @Override
    public void initialize(ServiceExtensionContext context) {
        var monitor = context.getMonitor();

        var vaultFile = context.getSetting(SEED_FILE, null);
        if (vaultFile == null || vaultFile.isBlank()) {
            vaultFile = context.getSetting(LEGACY_SEED_FILE, null);
            if (vaultFile != null && !vaultFile.isBlank()) {
                monitor.warning((
                    "%s is deprecated — it is the key EDC's own vault-filesystem module reads, and if that module "
                        + "is ever packaged the two collide silently. Rename it to %s; this fallback will be removed."
                    ).formatted(LEGACY_SEED_FILE, SEED_FILE));
            }
        }

        if (vaultFile == null || vaultFile.isBlank()) {
            // Not fatal: a deployment may one day bring its own Vault. It is a
            // warning rather than silence because with the current module set
            // there is no such backend, so this path means every vault alias
            // resolves to nothing.
            monitor.warning((
                "No vault seed file configured (%s). The only Vault on the classpath is EDC's in-memory default, "
                    + "so it will stay empty and every alias — the EDR signing key, the STS client secret — will "
                    + "fail to resolve."
                ).formatted(SEED_FILE));
            return;
        }

        var path = Path.of(vaultFile);
        if (!Files.exists(path)) {
            monitor.warning("Vault seed file not found: %s".formatted(path));
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
        monitor.info("Loaded %d secrets from %s".formatted(properties.size(), path));
    }
}
