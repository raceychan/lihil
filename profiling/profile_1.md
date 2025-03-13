  _     ._   __/__   _ _  _  _ _/_   Recorded: 21:22:56  Samples:  7884
 /_//_/// /_\ / //_// / //_'/ //     Duration: 13.286    CPU time: 10.077
/   _/                      v5.0.1

Program: app.py

```bash
13.285 <module>  app.py:1
└─ 13.187 run  lihil/server/runner.py:4
   └─ 13.187 Server.run  lihil/server/server.py:775
      └─ 13.187 run  asyncio/runners.py:160
         └─ 13.185 Runner.run  asyncio/runners.py:86
            ├─ 5.014 [self]  asyncio/runners.py
            ├─ 4.838 RequestResponseCycle.run_asgi  lihil/server/server.py:618
            │  ├─ 4.662 Lihil.__call__  lihil/lihil.py:20
            │  │  ├─ 4.376 Endpoint.__call__  lihil/routing.py:238
            │  │  │  ├─ 4.178 Endpoint.call_plain  lihil/routing.py:215
            │  │  │  │  ├─ 1.932 Endpoint.prepare_params  lihil/routing.py:173
            │  │  │  │  │  ├─ 1.571 Request.body  starlette/requests.py:238
            │  │  │  │  │  │     [3 frames hidden]  _weakrefset, starlette
            │  │  │  │  │  │        0.524 Request.stream  starlette/requests.py:218
            │  │  │  │  │  │        └─ 0.311 RequestResponseCycle.receive  lihil/server/server.py:741
            │  │  │  │  │  └─ 0.223 [self]  lihil/routing.py
            │  │  │  │  ├─ 1.305 Response.__call__  starlette/responses.py:147
            │  │  │  │  │  ├─ 0.776 RequestResponseCycle.send  lihil/server/server.py:639
            │  │  │  │  │  │  ├─ 0.397 [self]  lihil/server/server.py
            │  │  │  │  │  │  └─ 0.183 HttpToolsProtocol.on_response_complete  lihil/server/server.py:527
            │  │  │  │  │  └─ 0.529 [self]  starlette/responses.py
            │  │  │  │  ├─ 0.512 [self]  lihil/routing.py
            │  │  │  │  └─ 0.233 Response.__init__  starlette/responses.py:32
            │  │  │  │     └─ 0.143 Response.init_headers  starlette/responses.py:54
            │  │  │  └─ 0.197 [self]  lihil/routing.py
            │  │  └─ 0.181 [self]  lihil/lihil.py
            │  └─ 0.176 [self]  lihil/server/server.py
            └─ 3.280 HttpToolsProtocol.data_received  lihil/server/server.py:411
               ├─ 1.982 HttpToolsProtocol.on_headers_complete  lihil/server/server.py:468
               │  ├─ 1.026 WeakSet.add  _weakrefset.py:85
               │  ├─ 0.604 [self]  lihil/server/server.py
               │  └─ 0.212 Event.__init__  asyncio/locks.py:166
               ├─ 0.370 HttpToolsProtocol.on_header  lihil/server/server.py:462
               ├─ 0.353 HttpToolsProtocol.on_message_complete  lihil/server/server.py:520
               └─ 0.340 [self]  lihil/server/server.py
```

```bash
Running 10s test @ http://localhost:8000/
  2 threads and 10 connections
  Thread Stats   Avg      Stdev     Max   +/- Stdev
    Latency   215.14us   74.08us   1.29ms   66.11%
    Req/Sec    23.08k     1.50k   25.63k    57.50%
  459317 requests in 10.00s, 37.67MB read
Requests/sec:  45931.10
Transfer/sec:      3.77MB
```


| Function | File | Time Spent (s) | Analysis |
|----------|------|---------------|-----------|
| [self] asyncio/runners.py | asyncio/runners.py | 5.014 | Highest self time, indicating significant time in the asyncio runner itself |
| RequestResponseCycle.run_asgi | server/server.py | 0.176 | Time spent in ASGI cycle management (4.838 - 4.662) |
| Lihil.__call__ | lihil/lihil.py | 0.286 | Framework overhead (4.662 - 4.376) |
| Endpoint.__call__ | routing.py | 0.198 | Route dispatch (4.376 - 4.178) |
| WeakSet.add | *weakrefset.py | 1.026 | Notable time spent in weak reference management |
| HttpToolsProtocol.on_headers_complete | server/server.py | 0.604 | Self time in header processing |
| Request.body | requests.py | 1.047 | Time handling request body (1.571 - 0.524) |
| Response.__call__ | responses.py | 0.529 | Self time in response handling |
| Endpoint.prepare_params | routing.py | 0.223 | Self time in parameter preparation |
| HttpToolsProtocol.data_received | server/server.py | 0.340 | Self time in data reception |



