# ADR-0097: gRPC ingest for protobuf sources with a Struct envelope

- **ID:** ADR-0097
- **Timestamp:** 2026-11-21T08:55+01:00
- **Status:** Accepted
- **See:** REQUIREMENTS `ING-1`, `ING-2`, SPEC §4.2 and §6, DOMAIN §7, ADR-0061, ADR-0064, ADR-0065, ADR-0087

## Decision

**Wire format.** `contract/proto/pagercutie/v1/ingest.proto` defines `IngestService.Send(Event) returns (Accepted)`,
with `Event { google.protobuf.Struct payload = 1; }` and `Accepted { event_id, matches }` (the webhook's 202 body).
Every `protobuf` source uses this one message; sources still carry no schema config, and the decoded payload is
matched against the team's JSON Schemas like any other (ADR-0065). `mise run contract` generates
`backend/src/pagercutie/v1/ingest_pb2.py` and `.pyi` with `grpc_tools.protoc`; `contract:check` covers them.

**Transport.** Each replica runs a `grpc.aio` server on `APP_GRPC_PORT` (default 50051) as a worker beside the
FastAPI app, with server reflection so grpcurl needs no `.proto` file. Uvicorn has no HTTP/2 and ASGI has no
trailers, so gRPC cannot share the FastAPI port. Caddy enables h2c on `:8080` and routes requests with
`Content-Type: application/grpc*` to the replicas' port 50051, balanced per call. Producers and the demo reach gRPC
on the same origin as the UI, and the UI's grpcurl command is built from that origin.

**Source identity.** A gRPC method path has no parameters, so the slug goes in `source-slug` metadata next to
`authorization: Bearer <token>`. `INGEST_PATHS[protobuf]` is the method path `/pagercutie.v1.IngestService/Send`,
which `SourceRead.ingest_url` shows. Creating a `protobuf` source no longer answers 422.

**Adapter contract.** `SourceAdapter` becomes two protocols: `RouteAdapter` (`router()`, webhook and WebSocket) in
`ROUTE_ADAPTERS` and `ServerAdapter` (`worker(state, settings)`, gRPC) in `SERVER_ADAPTERS`. The unit test
compares the types of both tuples with `INGEST_PATHS`.

**Decoding.** The method is registered without a request deserializer, so the handler passes the raw bytes as
`RawEvent.body` and `ingest.decode` parses them once. The decoder is chosen by `RawEvent.source_type`, not
`content_type`, so webhook producers keep JSON decoding whatever header they send. Struct numbers are doubles:
integral values within ±2^53 become `int`, so `500` matches `"type": "integer"`, maps severity key `"500"` and
fingerprints like the same JSON body. NaN and infinities are rejected as `UNDECODABLE`.

**Replies.** `Accepted` once committed. Otherwise `context.abort` with `grpc_status(error)`: `NOT_FOUND`,
`UNAUTHENTICATED`, `INVALID_ARGUMENT` (the webhook's 422), `UNAVAILABLE` (503, the shared `IngestState` fails
closed as for HTTP), `UNIMPLEMENTED` (501). The server accepts messages up to 1 MiB, Caddy's webhook body limit.

**Demo.** `seed.py` creates `ledger-grpc` like the other sources. `load.py` keeps `--concurrency` unary calls in
flight per protobuf source on one channel to `DEMO_GRPC_TARGET` (`frontend:8080`), so the calls pass Caddy and the
netem delay like the other sources. The demo image builds from the repo root to copy the generated `ingest_pb2.py`.

## Options for the payload

| | Fixed envelope with `Struct` (chosen) | Producer's own `.proto` per source |
|---|---|---|
| Producer effort | Fill a Struct, or send JSON with grpcurl | Bring a descriptor set, send native messages |
| Data model | No change | Descriptor set and message name on sources, migration, upload UI |
| Type fidelity | Numbers are doubles; integers folded back up to 2^53 | Exact field types |
| Fit with ADR-0065 | Sources carry no schema config | Sources carry a wire schema next to the team's JSON Schemas |

## Options for the transport

| | gRPC server per replica (chosen) | Protobuf body over HTTP POST |
|---|---|---|
| Client | Any gRPC stack, grpcurl with reflection | curl with a binary file |
| Infrastructure | Second listener, h2c in Caddy | None |
| Streaming later | Native | Needs another framing |

## Options for the call shape

| | Unary `Send` only (chosen) | Also a bidirectional stream |
|---|---|---|
| Throughput | Calls multiplex over one HTTP/2 connection; the demo measured 620 events/s from one channel against 330 for one webhook source with 32 in flight | Similar |
| Errors | One status per event | A per-message error type so one bad event does not end the stream |
| Effort | One handler | Second handler, reply ordering, cancellation |

## Rationale

- The envelope covers `ING-1` with no data model change; per-source descriptors can be added later as another field.
- Real gRPC was the request; reflection and the UI's grpcurl command keep the paste-and-run test (`NFR-4`).
- One server per replica behind Caddy keeps the replica model (SPEC §3.2): any replica takes any call.
