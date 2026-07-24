package dataspaces.edc;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;
import org.eclipse.edc.spi.monitor.Monitor;

import java.io.IOException;
import java.time.Duration;
import java.util.Map;

/**
 * Thin HTTP transport to ds-connector's {@code /internal/*} API.
 *
 * <p>Every policy decision this connector makes is taken in Python; the Java
 * side only carries the question across. Centralising the transport keeps the
 * credential ({@link InternalAuth}), the retry schedule and the fail-closed
 * contract in one place rather than copied into each constraint function.
 *
 * <p><b>Fails closed.</b> {@link #getJson} returns {@code null} when the
 * connector is unreachable or answers non-2xx. Callers must treat {@code null}
 * as "denied", never as "unknown, so allow".
 */
public class ConnectorClient {

    private static final int[] BACKOFF_MS = {100, 500, 2000};
    private static final MediaType JSON = MediaType.get("application/json");

    private final String baseUrl;
    private final InternalAuth auth;
    private final OkHttpClient http;
    private final ObjectMapper mapper = new ObjectMapper();
    private final Monitor monitor;

    public ConnectorClient(String baseUrl, InternalAuth auth, Monitor monitor) {
        this.baseUrl = baseUrl.replaceAll("/+$", "");
        this.auth = auth;
        this.monitor = monitor;
        this.http = new OkHttpClient.Builder()
            .connectTimeout(Duration.ofSeconds(5))
            .readTimeout(Duration.ofSeconds(5))
            .build();
    }

    /**
     * GET {@code path} with {@code query}, retrying transport errors three times
     * (100 ms → 500 ms → 2 s).
     *
     * <p>A non-2xx answer is <em>not</em> retried: the connector reached a
     * decision and said no, so repeating the question cannot change it.
     *
     * @return the parsed body, or {@code null} on any failure.
     */
    public JsonNode getJson(String path, Map<String, String> query) {
        String url = url(path, query);
        for (int attempt = 0; attempt <= BACKOFF_MS.length; attempt++) {
            try {
                Request.Builder builder = new Request.Builder().url(url).get();
                auth.authorize(builder);
                try (Response response = http.newCall(builder.build()).execute()) {
                    if (!response.isSuccessful() || response.body() == null) {
                        monitor.warning("ConnectorClient: HTTP %d for %s".formatted(response.code(), path));
                        return null;
                    }
                    return mapper.readTree(response.body().string());
                }
            } catch (IOException e) {
                monitor.warning("ConnectorClient: attempt %d/%d for %s failed: %s"
                    .formatted(attempt + 1, BACKOFF_MS.length + 1, path, e.getMessage()));
                if (attempt < BACKOFF_MS.length) {
                    try {
                        Thread.sleep(BACKOFF_MS[attempt]);
                    } catch (InterruptedException ie) {
                        Thread.currentThread().interrupt();
                        return null;
                    }
                }
            }
        }
        return null;
    }

    /**
     * POST {@code body} as JSON to {@code path}, ignoring the response body.
     *
     * @return true when the connector accepted it.
     */
    public boolean postJson(String path, Object body) {
        return postJsonForResult(path, body) != null;
    }

    /**
     * POST {@code body} as JSON to {@code path}, with the same retry schedule.
     *
     * @return the parsed response, or {@code null} on any failure. An empty
     *         body yields an empty JSON object rather than {@code null}, so
     *         "accepted, said nothing" stays distinguishable from "failed".
     */
    public JsonNode postJsonForResult(String path, Object body) {
        String payload;
        try {
            payload = mapper.writeValueAsString(body);
        } catch (IOException e) {
            monitor.severe("ConnectorClient: could not serialise body for %s: %s".formatted(path, e.getMessage()));
            return null;
        }
        RequestBody requestBody = RequestBody.create(payload, JSON);
        for (int attempt = 0; attempt <= BACKOFF_MS.length; attempt++) {
            try {
                Request.Builder builder = new Request.Builder().url(baseUrl + path).post(requestBody);
                auth.authorize(builder);
                try (Response response = http.newCall(builder.build()).execute()) {
                    if (!response.isSuccessful()) {
                        monitor.warning("ConnectorClient: HTTP %d posting to %s".formatted(response.code(), path));
                        return null;
                    }
                    String text = response.body() == null ? "" : response.body().string();
                    return text.isBlank() ? mapper.createObjectNode() : mapper.readTree(text);
                }
            } catch (IOException e) {
                monitor.warning("ConnectorClient: attempt %d/%d posting to %s failed: %s"
                    .formatted(attempt + 1, BACKOFF_MS.length + 1, path, e.getMessage()));
                if (attempt < BACKOFF_MS.length) {
                    try {
                        Thread.sleep(BACKOFF_MS[attempt]);
                    } catch (InterruptedException ie) {
                        Thread.currentThread().interrupt();
                        return null;
                    }
                }
            }
        }
        return null;
    }

    private String url(String path, Map<String, String> query) {
        StringBuilder url = new StringBuilder(baseUrl).append(path);
        char separator = '?';
        for (Map.Entry<String, String> param : query.entrySet()) {
            if (param.getValue() == null || param.getValue().isEmpty()) {
                continue;
            }
            url.append(separator).append(param.getKey()).append('=').append(encode(param.getValue()));
            separator = '&';
        }
        return url.toString();
    }

    private static String encode(String value) {
        return java.net.URLEncoder.encode(value, java.nio.charset.StandardCharsets.UTF_8);
    }
}
