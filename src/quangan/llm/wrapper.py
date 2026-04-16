"""
LLM Client 可观测性包装器。

通过装饰器模式对任意 ILLMClient 进行透明包装，统一注入 DEBUG/ERROR 日志。
不修改原始 LLMClient / AnthropicClient 源码，也不引入自动重试，保持调用行为
与原实现完全一致，仅在日志层面增强白盒化观测能力。

未来如需接入 Metrics、Sentry 等 APM 工具，只需修改本文件一处即可。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from quangan.llm.types import (
    AgentCallRequest,
    AgentCallResponse,
    ChatMessage,
    ChatOptions,
    ILLMClient,
)
from quangan.utils.logger import get_logger

logger = get_logger("llm")


class LoggingClient(ILLMClient):
    """
    包装任意 ILLMClient，在保持接口完全兼容的前提下注入结构化日志。

    - DEBUG：记录请求规模（消息数）与响应长度
    - ERROR：记录失败原因，不吞掉异常
    - 不引入任何自动重试逻辑
    """

    def __init__(self, inner: ILLMClient) -> None:
        self._inner = inner

    @property
    def config(self) -> Any:
        """透传内部 client 的配置对象。"""
        return self._inner.config

    async def chat(self, messages: list[ChatMessage], options: ChatOptions | None = None) -> str:
        """记录请求规模，失败时记录 ERROR，成功后记录响应长度。"""
        logger.debug("LLM chat request: %d messages", len(messages))
        if options:
            logger.debug(
                "LLM chat options: temp=%s max_tokens=%s top_p=%s",
                options.temperature,
                options.max_tokens,
                options.top_p,
            )
        try:
            result = await self._inner.chat(messages, options)
            logger.debug("LLM chat response length: %d chars", len(result))
            return result
        except Exception:
            logger.error("LLM chat failed")
            raise

    async def chat_stream(
        self, messages: list[ChatMessage], options: ChatOptions | None = None
    ) -> AsyncGenerator[str, None]:
        """流式请求记录起点，失败时记录 ERROR。"""
        logger.debug("LLM stream request: %d messages", len(messages))
        try:
            async for chunk in self._inner.chat_stream(messages, options):
                yield chunk
        except Exception:
            logger.error("LLM stream failed")
            raise

    async def agent_call(self, req: AgentCallRequest) -> AgentCallResponse:
        """Agent 调用记录消息数与完成状态。"""
        logger.debug("LLM agent_call request: %d messages", len(req.messages))
        try:
            result = await self._inner.agent_call(req)
            logger.debug("LLM agent_call completed")
            return result
        except Exception:
            logger.error("LLM agent_call failed")
            raise

    async def ask(self, question: str, system_prompt: str | None = None) -> str:
        """单轮问答的日志包装。"""
        try:
            return await self._inner.ask(question, system_prompt)
        except Exception:
            logger.error("LLM ask failed")
            raise

    async def close(self) -> None:
        """透传关闭内部 client。"""
        await self._inner.close()
