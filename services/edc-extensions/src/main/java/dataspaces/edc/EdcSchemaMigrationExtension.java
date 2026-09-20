package dataspaces.edc;

import org.eclipse.edc.runtime.metamodel.annotation.Extension;
import org.eclipse.edc.runtime.metamodel.annotation.Inject;
import org.eclipse.edc.spi.system.ServiceExtension;
import org.eclipse.edc.spi.system.ServiceExtensionContext;
import org.eclipse.edc.sql.bootstrapper.SqlSchemaBootstrapper;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.UnaryOperator;

/**
 * Brings an EDC database created by an older EDC up to the schema of the pinned one.
 *
 * <h2>Why this exists</h2>
 *
 * <p>{@code edc.sql.schema.autocreate=true} runs the {@code *-schema.sql} file each SQL
 * store packages. Every one of them is {@code CREATE TABLE IF NOT EXISTS}, so a column a
 * newer EDC adds <b>never reaches a table an older EDC created</b>. EDC 0.17.0 and 0.18.0
 * added three columns that the contract-negotiation and transfer-process stores read and
 * write unconditionally. On a database from 0.16.0 every agreement fails to store
 * ({@code column "claims" of relation "edc_contract_agreement" does not exist}). The
 * counterparty then reports it as a {@code 401} on the agreement message, so it looks like
 * an authentication fault.
 *
 * <h2>How it works</h2>
 *
 * <p>EDC ships no migration tooling. It ships the {@link SqlSchemaBootstrapper}, and this
 * extension uses it: it queues ds's migration files on the same bootstrapper, against the
 * same datasource, as the store they migrate. So they run where the store DDL runs, in the
 * same transaction, and only when autocreate is on.
 *
 * <p>The bootstrapper's contract is that queued statements <b>must not rely on ordering</b>,
 * because the order is the extension order. Every migration is therefore
 * {@code ALTER TABLE IF EXISTS … ADD COLUMN IF NOT EXISTS}. Queued before the store's
 * {@code CREATE}, it skips a fresh database, and the {@code CREATE} then makes the new
 * shape. Queued after it, it adds the column to an old table, or finds it there. Running it
 * twice is the same as running it once.
 *
 * <p>The files are {@code ds-edc-schema/<store>/V<edc version>__<what>.sql} in this jar.
 * {@code <store>} is the key EDC uses in {@code edc.sql.store.<store>.datasource}.
 * Adding a file means adding it to {@link #MIGRATIONS}.
 * {@code EdcSchemaMigrationExtensionTest} fails if the two disagree. Why this and not
 * Flyway or a migration job: {@code docs/decisions/ADR-0018}.
 */
@Extension(EdcSchemaMigrationExtension.NAME)
public class EdcSchemaMigrationExtension implements ServiceExtension {

    static final String NAME = "Dataspaces EDC schema migrations";

    static final String AUTOCREATE = "edc.sql.schema.autocreate";

    static final String RESOURCE_ROOT = "ds-edc-schema";

    /** EDC's {@code DataSourceRegistry.DEFAULT_DATASOURCE}, the default of every store's datasource setting. */
    static final String DEFAULT_DATASOURCE = "default";

    /**
     * Store key → its migration files, oldest first. Covers databases created by EDC 0.16.0
     * or later. An older one needs the participant-context data migration, which is not
     * additive and is not here.
     */
    static final Map<String, List<String>> MIGRATIONS = migrations();

    @Inject
    private SqlSchemaBootstrapper bootstrapper;

    @Override
    public String name() {
        return NAME;
    }

    @Override
    public void initialize(ServiceExtensionContext context) {
        var monitor = context.getMonitor();
        var queued = queue(bootstrapper,
                store -> context.getSetting("edc.sql.store.%s.datasource".formatted(store), DEFAULT_DATASOURCE));

        if (context.getConfig().getBoolean(AUTOCREATE, false)) {
            monitor.info("Queued %d schema migration(s) with the SQL schema bootstrapper: %s"
                    .formatted(queued.size(), queued));
        } else {
            // Not fatal: running with autocreate off is a legitimate deployment choice, and the
            // operator then owns the DDL. But the store files alone do not upgrade an old
            // database, so the migrations have to be named where the operator will see them.
            monitor.warning(("%s is off, so neither the store schemas nor ds's schema migrations are applied. "
                    + "A database created by an older EDC must have these applied, in this order, from "
                    + "connector.jar: %s").formatted(AUTOCREATE, queued));
        }
    }

    /**
     * Queue every migration on {@code bootstrapper}, each against its store's datasource.
     *
     * @return the queued resource names, in the order queued
     */
    static List<String> queue(SqlSchemaBootstrapper bootstrapper, UnaryOperator<String> datasourceOfStore) {
        var queued = new ArrayList<String>();
        MIGRATIONS.forEach((store, resources) -> {
            var datasource = datasourceOfStore.apply(store);
            for (var resource : resources) {
                bootstrapper.addStatementFromResource(datasource, resource, EdcSchemaMigrationExtension.class.getClassLoader());
                queued.add(resource);
            }
        });
        return queued;
    }

    private static Map<String, List<String>> migrations() {
        var migrations = new LinkedHashMap<String, List<String>>();
        migrations.put("contractnegotiation", List.of(
                RESOURCE_ROOT + "/contractnegotiation/V0_17_0__agreement_claims.sql"));
        migrations.put("transferprocess", List.of(
                RESOURCE_ROOT + "/transferprocess/V0_17_0__transfer_claims.sql",
                RESOURCE_ROOT + "/transferprocess/V0_18_0__transfer_data_address_owner.sql"));
        return Collections.unmodifiableMap(migrations);
    }
}
