from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class FunctionCall(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str
    arguments: str


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    type: str = "function"
    function: FunctionCall


class ContentPart(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: str
    text: str | None = None


class Message(BaseModel):
    model_config = ConfigDict(extra="allow")
    role: str
    content: str | list[ContentPart] | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: str
    messages: list[Message]
    stream: bool = False


class ChoiceMessage(BaseModel):
    model_config = ConfigDict(extra="allow")
    role: str
    content: str | None = None
    tool_calls: list[ToolCall] | None = None


class Choice(BaseModel):
    model_config = ConfigDict(extra="allow")
    index: int
    message: ChoiceMessage
    finish_reason: str | None = None


class Usage(BaseModel):
    model_config = ConfigDict(extra="allow")
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    choices: list[Choice]
    usage: Usage | None = None
