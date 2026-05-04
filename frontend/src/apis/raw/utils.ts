import client from "./client";

type UrlTestResponse =
  | {
      status: true;
      version: string;
      code: number;
    }
  | {
      status: false;
      error: string;
      code: number;
    };

class RequestUtils {
  // Sonarr / Radarr connection tester. Backend builds the
  // /api/[v3/]system/status path itself and probes both with one call,
  // so the frontend only contributes scheme/host/port/base-url and the
  // service identifier. See LavX/bazarr#92 for why we no longer pass
  // the request path through the proxy.
  async urlTest(
    service: "sonarr" | "radarr",
    protocol: string,
    url: string,
    apikey: string,
  ) {
    const trimmed = url.replace(/\/+$/, "");
    const result = await client.axios.get<UrlTestResponse>(
      `../test/${service}`,
      { params: { url: `${protocol}://${trimmed}`, apikey } },
    );
    return result.data;
  }

  // Provider connection tester. Whisper-ASR runs the same
  // localhost-on-the-same-box pattern Sonarr/Radarr does (people
  // self-host transcription on the Bazarr box), so it goes through the
  // same constrained route. Backend appends /status itself; no apikey.
  async providerUrlTest(service: string, protocol: string, url: string) {
    const trimmed = url.replace(/\/+$/, "");
    const result = await client.axios.get<UrlTestResponse>(
      `../test/${service}`,
      { params: { url: `${protocol}://${trimmed}` } },
    );
    return result.data;
  }
}

const requestUtils = new RequestUtils();
export default requestUtils;
