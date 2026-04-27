import BaseApi from "./base";

interface JellyfinTestResult {
  success: boolean;
  server_name?: string;
  version?: string;
  // Coarse error classification only; raw exception text never crosses the
  // wire (see bazarr/jellyfin/operations.py::jellyfin_test_connection).
  error_code?: "configuration" | "connection_failed";
}

interface JellyfinRefreshResult {
  success: boolean;
  movies_total: number;
  movies_refreshed: number;
  series_total: number;
  series_refreshed: number;
  error_code?:
    | "configuration"
    | "connection_failed"
    | "no_libraries_configured";
}

interface JellyfinLibrary {
  id: string;
  name: string;
  type: string;
}

class JellyfinApi extends BaseApi {
  constructor() {
    super("/jellyfin");
  }

  async testConnection(url: string, apikey: string, verifySsl?: boolean) {
    const body: Record<string, string> = { url, apikey };
    if (verifySsl !== undefined) body.verify_ssl = verifySsl ? "true" : "false";
    const response = await this.post<JellyfinTestResult>(
      "/test-connection",
      body,
    );

    return response.data;
  }

  async libraries(url?: string, apikey?: string, verifySsl?: boolean) {
    const params: Record<string, string> = {};
    if (url) params.url = url;
    if (apikey) params.apikey = apikey;
    if (verifySsl !== undefined)
      params.verify_ssl = verifySsl ? "true" : "false";

    const response = await this.get<{ data: JellyfinLibrary[] }>(
      "/libraries",
      params,
    );

    return response.data;
  }

  async refreshLibraries() {
    const response = await this.post<JellyfinRefreshResult>(
      "/refresh-libraries",
      {},
    );
    return response.data;
  }
}

export default new JellyfinApi();
