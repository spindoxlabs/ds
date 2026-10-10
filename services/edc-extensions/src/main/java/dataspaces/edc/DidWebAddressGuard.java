package dataspaces.edc;

import okhttp3.Dns;

import java.net.Inet4Address;
import java.net.Inet6Address;
import java.net.InetAddress;
import java.net.UnknownHostException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

/**
 * Which addresses the EDC may dial for a did:web document (ADR-0029, extended).
 *
 * <p>The rules of {@code ds_auth.address_guard}, which the identity registry, the
 * connector and provenance apply; in Java because the EDC resolves did:web itself.
 * The host of a did:web identifier is chosen by whoever presents the DID, so every
 * address it resolves to is checked before OkHttp connects ({@link GuardedDns}:
 * OkHttp dials exactly the addresses a {@code Dns} returns):
 * <ul>
 *   <li>link-local (cloud metadata), multicast, reserved and unspecified: never;</li>
 *   <li>public: always;</li>
 *   <li>private (RFC 1918, unique-local, the documentation ranges) and loopback:
 *       only under {@code DS_ENV=dev};</li>
 *   <li>otherwise only a host under a listed suffix resolving into a listed private
 *       network ({@link Allowance}, empty by default).</li>
 * </ul>
 * Mirrors the Python rules on their test vectors; on a few special-purpose ranges
 * Python's {@code ipaddress} treats as private (e.g. {@code 0.0.0.0/8} other than
 * {@code 0.0.0.0}) it is stricter.
 */
final class DidWebAddressGuard {

    static final String NEVER = "a link-local, multicast, reserved or unspecified address";
    static final String NON_PUBLIC = "a non-public address";

    /** Not globally routable, beyond link-local/multicast/unspecified/reserved. */
    private static final List<Cidr> NON_GLOBAL = Cidr.list(
        "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "172.16.0.0/12", "192.0.0.0/24",
        "192.0.2.0/24", "192.168.0.0/16", "198.18.0.0/15", "198.51.100.0/24", "203.0.113.0/24",
        "::1/128", "fc00::/7", "2001::/23", "2001:db8::/32", "2002::/16", "64:ff9b:1::/48", "100::/64");

    /** What {@code DS_ENV=dev} admits on top of public: the local topology. */
    private static final List<Cidr> DEV_PRIVATE = Cidr.list(
        "10.0.0.0/8", "127.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "192.0.2.0/24", "198.18.0.0/15",
        "198.51.100.0/24", "203.0.113.0/24", "::1/128", "fc00::/7", "2001:db8::/32");

    /** IPv6 space with an assignment; outside it everything is reserved. */
    private static final List<Cidr> IPV6_ASSIGNED = Cidr.list("2000::/3", "fc00::/7", "fe80::/10", "ff00::/8",
        "::1/128", "::/128", "64:ff9b::/96", "64:ff9b:1::/48", "100::/64");

    private static final Cidr IPV4_RESERVED = Cidr.parse("240.0.0.0/4");
    private static final Pattern SUFFIX = Pattern.compile("^(\\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?){2,}$");

    private DidWebAddressGuard() {
    }

    /** Why {@code ip} may not be dialled for {@code host}, or {@code null} when it may. */
    static String refusal(InetAddress address, boolean dev, String host, Allowance allowance) {
        var ip = unmapped(address);
        if (ip.isLinkLocalAddress() || ip.isMulticastAddress() || ip.isAnyLocalAddress() || reserved(ip)) {
            return NEVER;
        }
        if (NON_GLOBAL.stream().noneMatch(c -> c.contains(ip))) {
            return null;
        }
        if (dev && DEV_PRIVATE.stream().anyMatch(c -> c.contains(ip))) {
            return null;
        }
        if (allowance != null && allowance.admits(host, ip)) {
            return null;
        }
        return NON_PUBLIC;
    }

    /** Every address must pass, not just the first; the refusal names the host and address. */
    static List<InetAddress> admitted(String host, List<InetAddress> addresses, boolean dev, Allowance allowance)
        throws UnknownHostException {
        if (addresses.isEmpty()) {
            throw new UnknownHostException(host + " resolves to no address");
        }
        for (var ip : addresses) {
            var reason = refusal(ip, dev, host, allowance);
            if (reason != null) {
                throw new UnknownHostException(host + " resolves to " + reason + " (" + ip.getHostAddress() + ")");
            }
        }
        return addresses;
    }

    private static boolean reserved(InetAddress ip) {
        if (ip instanceof Inet4Address) {
            return IPV4_RESERVED.contains(ip);
        }
        return IPV6_ASSIGNED.stream().noneMatch(c -> c.contains(ip));
    }

    private static InetAddress unmapped(InetAddress ip) {
        if (ip instanceof Inet6Address) {
            var b = ip.getAddress();
            var mapped = true;
            for (int i = 0; i < 10; i++) {
                mapped &= b[i] == 0;
            }
            if (mapped && b[10] == (byte) 0xff && b[11] == (byte) 0xff) {
                try {
                    return InetAddress.getByAddress(Arrays.copyOfRange(b, 12, 16));
                } catch (UnknownHostException e) {
                    return ip;
                }
            }
        }
        return ip;
    }

    /** An OkHttp {@code Dns} that returns only admitted addresses, or refuses the name. */
    static final class GuardedDns implements Dns {
        private final Dns delegate;
        private final boolean dev;
        private final Allowance allowance;

        GuardedDns(Dns delegate, boolean dev, Allowance allowance) {
            this.delegate = delegate;
            this.dev = dev;
            this.allowance = allowance;
        }

        @Override
        public List<InetAddress> lookup(String hostname) throws UnknownHostException {
            return admitted(hostname, delegate.lookup(hostname), dev, allowance);
        }
    }

    /**
     * The dataspace's own host suffixes and the private networks they may resolve to.
     * Both or neither; a one-label suffix, a wildcard, a default route, or a public,
     * link-local or loopback network is refused when parsed (at start).
     */
    record Allowance(List<String> suffixes, List<Cidr> networks) {
        static final Allowance NONE = new Allowance(List.of(), List.of());

        static Allowance parse(String hosts, String networks) {
            var hostItems = items(hosts).stream().map(h -> h.toLowerCase(Locale.ROOT).replaceAll("\\.$", "")).toList();
            var netItems = items(networks);
            if (hostItems.isEmpty() && netItems.isEmpty()) {
                return NONE;
            }
            if (hostItems.isEmpty() || netItems.isEmpty()) {
                throw new IllegalArgumentException("did:web internal allowance: set both the host suffixes and the "
                    + "networks they may resolve to, or neither");
            }
            var suffixes = new ArrayList<String>();
            for (var h : hostItems) {
                var suffix = h.startsWith(".") ? h : "." + h;
                if (!SUFFIX.matcher(suffix).matches()) {
                    throw new IllegalArgumentException("did:web internal allowance: '" + h + "' is not a host suffix "
                        + "of at least two DNS labels (e.g. .ds.example.org)");
                }
                suffixes.add(suffix);
            }
            var nets = new ArrayList<Cidr>();
            for (var n : netItems) {
                Cidr net;
                try {
                    net = Cidr.parse(n);
                } catch (IllegalArgumentException e) {
                    throw new IllegalArgumentException("did:web internal allowance: '" + n + "' is not a network", e);
                }
                var loopback = net.within(Cidr.parse("127.0.0.0/8")) || net.within(Cidr.parse("::1/128"));
                var privateRange = DEV_PRIVATE.stream().anyMatch(net::within);
                if (net.prefix() == 0 || loopback || !privateRange) {
                    throw new IllegalArgumentException("did:web internal allowance: network '" + n + "' is not a "
                        + "private network this allowance may name (no default route, public, link-local, loopback "
                        + "or multicast range)");
                }
                nets.add(net);
            }
            return new Allowance(List.copyOf(suffixes), List.copyOf(nets));
        }

        boolean active() {
            return !suffixes.isEmpty();
        }

        boolean admits(String host, InetAddress ip) {
            var name = host.toLowerCase(Locale.ROOT).replaceAll("\\.$", "");
            return suffixes.stream().anyMatch(name::endsWith) && networks.stream().anyMatch(n -> n.contains(ip));
        }

        String describe() {
            return "hosts under " + String.join(", ", suffixes) + " may resolve to "
                + networks.stream().map(Cidr::toString).collect(Collectors.joining(", "));
        }

        private static List<String> items(String csv) {
            if (csv == null) {
                return List.of();
            }
            return Arrays.stream(csv.split(",")).map(String::trim).filter(s -> !s.isEmpty()).toList();
        }
    }

    /** An IPv4 or IPv6 network. */
    record Cidr(byte[] network, int prefix, String text) {

        static Cidr parse(String text) {
            var parts = text.trim().split("/", -1);
            if (parts.length > 2 || parts[0].isEmpty() || !parts[0].matches("[0-9a-fA-F:.]+")) {
                throw new IllegalArgumentException(text);
            }
            byte[] address;
            try {
                address = InetAddress.getByName(parts[0]).getAddress();
            } catch (UnknownHostException e) {
                throw new IllegalArgumentException(text, e);
            }
            int bits = address.length * 8;
            int prefix;
            try {
                prefix = parts.length == 2 ? Integer.parseInt(parts[1]) : bits;
            } catch (NumberFormatException e) {
                throw new IllegalArgumentException(text, e);
            }
            if (prefix < 0 || prefix > bits) {
                throw new IllegalArgumentException(text);
            }
            return new Cidr(mask(address, prefix), prefix, text.trim());
        }

        static List<Cidr> list(String... texts) {
            return Arrays.stream(texts).map(Cidr::parse).toList();
        }

        boolean contains(InetAddress ip) {
            var b = ip.getAddress();
            return b.length == network.length && Arrays.equals(mask(b, prefix), network);
        }

        boolean within(Cidr other) {
            return network.length == other.network.length && prefix >= other.prefix
                && Arrays.equals(mask(network, other.prefix), other.network);
        }

        private static byte[] mask(byte[] address, int prefix) {
            var out = address.clone();
            for (int i = 0; i < out.length; i++) {
                int keep = Math.max(0, Math.min(8, prefix - i * 8));
                out[i] = (byte) (out[i] & (0xff << (8 - keep)));
            }
            return out;
        }

        @Override
        public String toString() {
            return text;
        }
    }
}
