# Socket Channel 实时协议能力 PRD

## 1. 背景

Lihil 当前已经有 `SocketHub`、`ChannelBase`、`MessageEnvelope`、`SocketBus` 等 WebSocket channel 抽象，能够支持 topic 匹配、join/leave、连接生命周期 hook 和 topic fanout。

这套能力已经足够做简单聊天室或 demo，但如果 Lihil 要作为后续多端产品的实时协议层，还需要补齐客户端状态机、请求响应配对、断线恢复、长任务生命周期和事件分发语义。

本 PRD 以“Lihil 自身产品能力”为目标，不为某个业务项目硬编码特殊协议。AceAI GUI、Electron 客户端、React Web、iOS 客户端都应该能够基于同一套 channel 协议建模。

## 2. 目标

- 让 Lihil channel 能承载产品级实时交互，而不只是简单 fanout。
- 提供稳定的 envelope 协议，支持客户端请求和服务端响应配对。
- 明确 join/leave/错误/ack 语义，方便 Web、Electron、iOS 编写可靠状态机。
- 支持按 event 名自动分发到 channel handler，减少业务 channel 手写分发逻辑。
- 支持 channel 内长任务管理，在连接断开、leave、异常时能统一清理。
- 为断线重连和事件补偿留出标准协议入口。

## 3. 非目标

- 不实现某个业务系统的 session/run/message API。
- 不要求 Lihil 复制 Phoenix Channels 的完整实现。
- 不在本阶段实现分布式 PubSub 后端，但 API 设计要允许后续替换 `SocketBus`。
- 不在本阶段实现客户端 SDK，但协议要足够稳定，后续可以生成或手写 SDK。
- 不改变普通 HTTP route、DI、OpenAPI 的既有语义。

## 4. 现状

当前核心能力：

- `MessageEnvelope` 包含 `topic`、`event`、`payload`。
- `Topic("room:{room_id}")` 能把 topic pattern 编译为带命名参数的正则。
- `ChannelBase` 提供 `on_join()`、`on_message(env)`、`on_leave()`。
- `ChannelBase.publish()` 和 `emit()` 能通过 bus 向当前 resolved topic fanout。
- `SocketSession.handle_message()` 处理 `join`、`leave` 和普通事件。
- `SocketHub.channel()` 注册 channel 类型，并按 topic pattern 匹配创建 channel。
- `SocketBus` 默认实现为进程内 `InMemorySocketBus`。

当前主要缺口：

- Envelope 没有 `ref`、`join_ref`、`event_id`、`seq` 等字段。
- join 成功不会返回标准 ack，duplicate join 也不会给客户端明确反馈。
- 文档提到的 `on_<event>` 自动分发尚未在代码中实现。
- 业务 handler 返回值和错误响应缺少统一 envelope 格式。
- Channel 没有内建 task lifecycle，长任务需要业务代码自己管理。
- 没有标准 reconnect/replay 协议入口。

## 5. 用户故事

### 5.1 客户端加入 topic

作为 Web/iOS 客户端，我发送带 `ref` 的 `join` 消息后，希望收到带同一个 `ref` 的明确响应，知道 join 是成功、失败、还是已经加入。

### 5.2 客户端发送命令

作为客户端，我发送 `send_message`、`cancel`、`approve_tool` 等命令后，希望服务端响应能和请求配对，而不是只能依赖后续事件流猜测命令是否成功。

### 5.3 服务端推送事件

作为客户端，我希望每条服务端事件都携带稳定 envelope 字段，能够按 topic、event、event_id、seq 更新本地状态。

### 5.4 断线恢复

作为移动端客户端，我断线重连后，希望能在 join payload 中带上 `last_event_id` 或 `since`，服务端补发缺失事件或明确告诉我需要重新拉取 snapshot。

### 5.5 长任务清理

作为业务 channel 作者，我希望在 channel 中启动流式任务后，客户端 leave 或断开连接时，Lihil 自动取消并清理这些任务。

## 6. 协议设计

### 6.1 入站 Envelope

客户端发给服务端的消息应支持：

```json
{
  "topic": "session:abc",
  "event": "join",
  "payload": {},
  "ref": "1",
  "join_ref": null
}
```

字段说明：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `topic` | string | 是 | 目标 topic |
| `event` | string | 是 | 事件名，例如 `join`、`leave`、`send_message` |
| `payload` | any | 否 | 事件载荷 |
| `ref` | string \| null | 否 | 客户端请求 id，用于响应配对 |
| `join_ref` | string \| null | 否 | 当前 topic join 的引用 id，用于区分同一 socket 上的 topic 生命周期 |

### 6.2 出站 Envelope

服务端发给客户端的消息应支持：

```json
{
  "topic": "session:abc",
  "event": "reply",
  "payload": {
    "status": "ok",
    "response": {}
  },
  "ref": "1",
  "join_ref": "1",
  "event_id": "evt_123",
  "seq": 12
}
```

字段说明：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `topic` | string | 是 | 目标 topic |
| `event` | string | 是 | 服务端事件名 |
| `payload` | any | 否 | 事件载荷 |
| `ref` | string \| null | 否 | 若是请求响应，必须回填客户端 ref |
| `join_ref` | string \| null | 否 | 当前 topic 生命周期引用 |
| `event_id` | string \| null | 否 | 服务端事件 id；可用于 replay |
| `seq` | int \| null | 否 | 连接内单调序号；可用于客户端排序和调试 |

### 6.3 标准 Reply Payload

请求响应统一使用：

```json
{
  "status": "ok",
  "response": {}
}
```

失败响应统一使用：

```json
{
  "status": "error",
  "error": {
    "code": "topic_not_found",
    "message": "Topic not found",
    "detail": {}
  }
}
```

建议内置错误码：

| code | 场景 |
| --- | --- |
| `topic_not_found` | 没有 channel 能匹配 topic |
| `event_not_found` | channel 不支持该 event |
| `join_rejected` | channel 拒绝加入 |
| `invalid_payload` | payload 校验失败 |
| `internal_error` | 服务端未预期错误 |
| `already_joined` | topic 已加入；是否算 error 由实现决定 |
| `not_joined` | 未加入 topic 却发送普通事件 |

## 7. Channel API 设计

### 7.1 自动事件分发

`SocketSession` 在收到普通事件后应优先查找 channel 上的事件 handler：

```python
async def on_send_message(self, payload: SendMessagePayload, env: MessageEnvelope) -> Reply:
    ...
```

分发规则：

- `event="send_message"` 映射到 `on_send_message`。
- handler 可接受 `payload`、`env`，具体签名应保持简单明确。
- 如果 handler 不存在，回 `event_not_found`。
- 如果 handler 返回非 `None`，通过标准 reply envelope 返回。
- 如果 handler 自行 publish/emit，也可以返回 `None`。
- `join` 和 `leave` 继续走生命周期方法，不走普通 `on_<event>`。

### 7.2 Join 语义

`join` 成功后必须返回标准 ack：

```json
{
  "status": "ok",
  "response": {
    "topic": "session:abc"
  }
}
```

建议规则：

- 首次 join：创建 channel，调用 `on_join()`，记录 subscription，返回 ok。
- duplicate join：不重复订阅，返回 ok，并在 response 中标记 `already_joined: true`。
- topic 不匹配：返回 `topic_not_found`。
- `on_join()` 主动拒绝：返回 `join_rejected`。

### 7.3 Leave 语义

`leave` 成功后必须返回标准 ack。

建议规则：

- 已加入 topic：调用 `on_leave()`，取消 channel tasks，移除 subscription，返回 ok。
- 未加入 topic：返回 `not_joined`。
- 连接断开时：对所有已加入 channel 执行 leave 清理，但不需要向已断开的客户端发送 ack。

### 7.4 Channel Task Lifecycle

`ChannelBase` 应提供最小 task 管理能力：

```python
self.start_task("run_stream", coro)
await self.cancel_task("run_stream")
await self.cancel_tasks()
```

要求：

- task 名称在同一 channel 实例内唯一。
- leave/disconnect 时自动 cancel 所有 tasks。
- task 异常应可配置为：关闭 socket、发送 error event、或记录后忽略。
- MVP 阶段可以先实现自动 cancel 和测试覆盖，不必引入复杂 supervision。

### 7.5 Replay Hook

为断线恢复预留 channel hook：

```python
async def replay_after(self, event_id: str | None) -> list[SocketEnvelope]:
    ...
```

建议规则：

- 客户端可在 join payload 中传 `last_event_id`。
- channel 如果支持 replay，则 join ack 后补发缺失事件。
- channel 如果不支持 replay，应返回 ok，并在 response 中声明 `replay_supported: false`。
- replay 数据来源由业务 channel 决定，Lihil 只定义协议入口。

## 8. SocketBus 要求

MVP 阶段保留 `InMemorySocketBus`，但接口语义要更清晰：

- `publish()` 是阻塞 fanout，调用方等待所有当前 subscriber 处理完成。
- `emit()` 是 fire-and-forget fanout。
- subscriber 异常时当前实现会移除 callback；需要在文档和测试中明确。
- 后续可以增加 Redis/Postgres/Kafka 等 bus 实现，但本 PRD 不要求实现。

## 9. 兼容性策略

Lihil 当前还未形成稳定的 channel 协议版本，因此本阶段可以接受 breaking change。

建议：

- 直接升级 `MessageEnvelope`，不保留旧 envelope 的兼容 shim。
- 测试统一改成新 envelope。
- 文档示例统一使用新协议。
- 如果需要短期支持旧 payload，应由业务层自己适配，不放进 Lihil core。

## 10. 验收标准

### 10.1 协议模型

- `MessageEnvelope` 支持 `topic/event/payload/ref/join_ref`。
- 服务端出站 envelope 支持 `topic/event/payload/ref/join_ref/event_id/seq`。
- 标准 reply/error payload 有明确类型和测试。

### 10.2 Join/Leave

- join 成功返回带原 `ref` 的 ok reply。
- duplicate join 不重复订阅，并返回明确结果。
- unknown topic 返回标准 `topic_not_found` error。
- leave 成功返回 ok reply。
- 未加入 topic 时 leave 返回标准 `not_joined` error。
- disconnect 时所有 joined channels 都执行 cleanup。

### 10.3 Event Dispatch

- `event="send_message"` 能自动调用 `on_send_message`。
- 不存在的 event 返回 `event_not_found`。
- handler 返回值能通过标准 reply envelope 发回。
- handler 内 publish/emit 仍然可用。

### 10.4 Task Lifecycle

- channel 能启动命名 task。
- leave 时 task 被取消。
- disconnect 时 task 被取消。
- task 异常行为有测试覆盖。

### 10.5 Replay Hook

- join payload 可以携带 `last_event_id`。
- 支持 replay 的 channel 能在 join 后补发事件。
- 不支持 replay 的 channel 能在 join response 中明确声明。

### 10.6 文档

- README 或 Copilot 文档中的 channel 示例和真实代码一致。
- 文档不再声明未实现的 `on_<event>` 行为。
- 至少包含一个完整示例：join、send event、server reply、broadcast、leave。

## 11. 建议实施顺序

### Phase 1: Envelope 和 Reply 基础

- 扩展 `MessageEnvelope`。
- 增加出站 envelope/reply/error helper。
- 更新 `ISocket.reply()`、`ISocket.emit()`。
- 更新现有 hub tests。

### Phase 2: Join/Leave 语义

- join 成功返回 ok ack。
- duplicate join 返回明确 ack。
- leave 返回 ok 或 `not_joined`。
- 错误统一走标准 error payload。

### Phase 3: 自动事件分发

- 实现 `on_<event>` dispatch。
- 保留 `on_message(env)` 作为 fallback 或显式默认入口。
- 更新文档，使文档和代码一致。

### Phase 4: Channel Task Lifecycle

- 在 `ChannelBase` 中增加 task registry。
- leave/disconnect 时统一 cancel。
- 添加长任务 cleanup 测试。

### Phase 5: Replay Hook

- 定义 join payload 中的 `last_event_id` 约定。
- 增加 `replay_after()` hook。
- 添加一个内存事件 replay 示例和测试。

## 12. 后续产品化方向

- 提供 TypeScript client SDK。
- 提供 Swift client SDK。
- 支持跨进程或分布式 bus。
- 增加 heartbeat/ping-pong 语义。
- 增加 channel-level auth/authorization hook。
- 增加 OpenAPI-like channel schema 或文档生成。
- 增加连接级 tracing/debug events。

