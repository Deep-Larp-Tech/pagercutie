import { login } from "../../frontend/src/api/generated/auth/auth";
import type { MeRead } from "../../frontend/src/api/generated/model";

/** What every generated client function resolves to, for any status (ADR-0045). */
interface ApiResponse {
  status: number;
  data: unknown;
  headers: Headers;
}

/** A generated client function (`getMe`, `createUser`, ...): endpoint arguments, then an optional `RequestInit`. */
export type Operation<Args extends unknown[], Response extends ApiResponse> = (
  ...args: [...Args, RequestInit?]
) => Promise<Response>;

/** Body the contract documents for `Response` at `status`. */
export type DataAt<Response extends ApiResponse, Status extends Response["status"]> = Extract<
  Response,
  { status: Status }
>["data"];

/** A response with a status the caller did not expect; names the generated function that got it. */
export class ApiError extends Error {
  constructor(
    readonly operation: string,
    readonly status: number,
    readonly body: string,
  ) {
    super(`${operation} answered ${status}: ${body}`);
    this.name = "ApiError";
  }
}

const SESSION_COOKIE = "pc_session";

/**
 * Calls the generated client functions with one session's `pc_session` cookie.
 *
 * The functions resolve their URLs against `setApiBaseUrl` (set once per worker by the fixtures); `baseURL` here is
 * for raw probes and for adding the cookie to a browser context.
 */
export class ApiClient {
  private constructor(
    readonly baseURL: string,
    readonly session: string | undefined,
  ) {}

  /** A client without a session, for routes that need none (`login`, `getHealth`) or to assert `401`. */
  static anonymous(baseURL: string): ApiClient {
    return new ApiClient(baseURL, undefined);
  }

  /** Logs in as `email` and returns a client holding the new session, plus the `MeRead` the login returned. */
  static async login(baseURL: string, email: string): Promise<{ api: ApiClient; me: MeRead }> {
    const response = await login({ email });
    if (response.status !== 200) {
      throw new ApiError(login.name, response.status, JSON.stringify(response.data));
    }
    return { api: new ApiClient(baseURL, sessionFrom(response.headers)), me: response.data };
  }

  /** `Cookie` header value for this session; empty when anonymous. */
  get cookieHeader(): string {
    return this.session === undefined ? "" : `${SESSION_COOKIE}=${this.session}`;
  }

  /** Calls `operation` with this session and resolves to its `{ status, data, headers }` for any status. */
  call<Args extends unknown[], Response extends ApiResponse>(
    operation: Operation<Args, Response>,
    ...args: Args
  ): Promise<Response> {
    const init: RequestInit = this.session === undefined ? {} : { headers: { cookie: this.cookieHeader } };
    return operation(...args, init);
  }

  /**
   * Calls `operation` and returns its body when it answers `status`. Throws `ApiError` on any other status, so a
   * fixture can tell a `501` stub (`skipIfNotImplemented`) from a real failure.
   */
  async callExpecting<Args extends unknown[], Response extends ApiResponse, Status extends Response["status"]>(
    operation: Operation<Args, Response>,
    status: Status,
    ...args: Args
  ): Promise<DataAt<Response, Status>> {
    const response = await this.call(operation, ...args);
    if (!isStatus(response, status)) {
      throw new ApiError(operation.name, response.status, JSON.stringify(response.data));
    }
    return response.data;
  }
}

function isStatus<Response extends ApiResponse, Status extends Response["status"]>(
  response: Response,
  status: Status,
): response is Extract<Response, { status: Status }> {
  return response.status === status;
}

function sessionFrom(headers: Headers): string {
  for (const cookie of headers.getSetCookie()) {
    const [pair] = cookie.split(";");
    const separator = pair.indexOf("=");
    if (pair.slice(0, separator).trim() === SESSION_COOKIE) return pair.slice(separator + 1);
  }
  throw new Error(`login answered 200 without a ${SESSION_COOKIE} cookie`);
}
