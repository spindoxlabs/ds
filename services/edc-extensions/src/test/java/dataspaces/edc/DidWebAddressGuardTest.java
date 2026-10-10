package dataspaces.edc;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.ValueSource;

import java.net.InetAddress;
import java.net.UnknownHostException;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * The EDC's did:web address guard: the rules of {@code ds_auth.address_guard}
 * (ADR-0029, extended), in Java because the EDC resolves did:web itself.
 *
 * <p>Same vectors as {@code libs/ds-auth/tests/test_address_guard.py}: public only
 * under production; private and loopback too under {@code DS_ENV=dev}; link-local
 * (metadata), multicast, reserved and unspecified never; every resolved address;
 * and the optional allowance of the dataspace's own host suffixes and networks.
 */
class DidWebAddressGuardTest {

    private static final DidWebAddressGuard.Allowance ALLOW =
        DidWebAddressGuard.Allowance.parse(".ds.example.org", "10.96.0.0/12,fd00:10::/64");

    private static InetAddress ip(String literal) throws UnknownHostException {
        return InetAddress.getByName(literal);
    }

    @ParameterizedTest
    @ValueSource(strings = {"10.0.0.5", "172.16.3.4", "192.168.1.1", "127.0.0.1", "100.64.0.1", "::1",
        "fd00::1", "169.254.169.254", "fe80::1", "0.0.0.0", "224.0.0.1", "240.0.0.1"})
    void aNonPublicAddressIsRefusedOutsideDev(String address) throws Exception {
        assertTrue(DidWebAddressGuard.refusal(ip(address), false, "host.example.org", null) != null, address);
    }

    @ParameterizedTest
    @ValueSource(strings = {"169.254.169.254", "fe80::1", "0.0.0.0", "224.0.0.1", "240.0.0.1"})
    void linkLocalAndUnroutableAreRefusedEvenInDev(String address) throws Exception {
        var reason = DidWebAddressGuard.refusal(ip(address), true, "host.example.org", ALLOW);
        assertTrue(reason != null && reason.contains("link-local"), address + ": " + reason);
    }

    @ParameterizedTest
    @ValueSource(strings = {"10.0.0.5", "172.18.0.7", "127.0.0.1", "::1"})
    void devAdmitsTheLocalTopology(String address) throws Exception {
        assertNull(DidWebAddressGuard.refusal(ip(address), true, "rec.dataspaces.localhost", null));
    }

    @Test
    void aPublicAddressIsAdmitted() throws Exception {
        assertNull(DidWebAddressGuard.refusal(ip("93.184.216.34"), false, "host.example.org", null));
    }

    @Test
    void everyAnswerMustBeAdmissible() throws Exception {
        var refused = assertThrows(UnknownHostException.class, () -> DidWebAddressGuard.admitted(
            "host.example.org", List.of(ip("93.184.216.34"), ip("10.0.0.5")), false, null));
        assertTrue(refused.getMessage().contains("non-public"), refused.getMessage());
        assertEquals(List.of(ip("93.184.216.34")),
            DidWebAddressGuard.admitted("host.example.org", List.of(ip("93.184.216.34")), false, null));
    }

    @Test
    void theAllowanceAdmitsOnlyItsHostsIntoItsNetworks() throws Exception {
        assertNull(DidWebAddressGuard.refusal(ip("10.96.0.10"), false, "trust-anchor.ds.example.org", ALLOW));
        assertNull(DidWebAddressGuard.refusal(ip("fd00:10::5"), false, "Holder.DS.Example.org.", ALLOW));
        for (var host : List.of("attacker.example.net", "ds.example.org.attacker.net", "evilds.example.org",
            "ds.example.org")) {
            assertTrue(DidWebAddressGuard.refusal(ip("10.96.0.10"), false, host, ALLOW) != null, host);
        }
        assertTrue(DidWebAddressGuard.refusal(ip("192.168.1.5"), false, "a.ds.example.org", ALLOW) != null);
    }

    @ParameterizedTest
    @CsvSource(value = {
        ".ds.example.org|",
        "|10.0.0.0/8",
        ".org|10.0.0.0/8",
        "*.example.org|10.0.0.0/8",
        ".ds.example.org|0.0.0.0/0",
        ".ds.example.org|::/0",
        ".ds.example.org|8.8.8.0/24",
        ".ds.example.org|169.254.0.0/16",
        ".ds.example.org|127.0.0.0/8",
        ".ds.example.org|not-a-network",
    }, delimiter = '|')
    void anUnsoundAllowanceIsRefused(String hosts, String networks) {
        assertThrows(IllegalArgumentException.class, () -> DidWebAddressGuard.Allowance.parse(
            hosts == null ? "" : hosts, networks == null ? "" : networks));
    }

    @Test
    void theEmptyAllowanceIsEmptyAndASingleHostIsA32() throws Exception {
        assertFalse(DidWebAddressGuard.Allowance.parse("", "").active());
        var one = DidWebAddressGuard.Allowance.parse("ds.example.org", "192.168.1.10/32");
        assertTrue(one.admits("a.ds.example.org", ip("192.168.1.10")));
        assertFalse(one.admits("a.ds.example.org", ip("192.168.1.11")));
        assertEquals("hosts under .ds.example.org may resolve to 192.168.1.10/32", one.describe());
    }
}
