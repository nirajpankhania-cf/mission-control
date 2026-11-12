"""The single interface every model call goes through.

Two implementations exist: ``AnthropicClient`` for the real API and
``FakeModelClient`` for tests and for running without an API key. The
pipeline only ever sees ``ModelClient``.
"""


class ModelError(Exception):
    """Raised by a client when a call fails or the reply is unusable."""


class ModelRequest(object):
    """One structured call.

    ``task`` names the step (sort, check_hidden, check_missing, check_panic,
    draft, review). ``system`` and ``prompt`` are the texts sent to the model,
    ``schema`` the JSON schema the reply must follow. ``context`` holds the
    structured fields the prompt was built from; the fake uses it to produce
    sensible replies and the real client never sends it.
    """

    def __init__(self, task, model, system, prompt, schema, max_tokens=1024,
                 effort="low", context=None):
        self.task = task
        self.model = model
        self.system = system
        self.prompt = prompt
        self.schema = schema
        self.max_tokens = max_tokens
        self.effort = effort
        self.context = context or {}

    def __repr__(self):
        return "ModelRequest(task=%r, model=%r)" % (self.task, self.model)


class ModelReply(object):
    """What a client returns: parsed JSON plus the usage needed for cost."""

    def __init__(self, data, text, input_tokens, output_tokens, model, stop_reason="end_turn"):
        self.data = data
        self.text = text
        self.input_tokens = int(input_tokens)
        self.output_tokens = int(output_tokens)
        self.model = model
        self.stop_reason = stop_reason

    def __repr__(self):
        return "ModelReply(model=%r, tokens=%d/%d)" % (self.model, self.input_tokens, self.output_tokens)


class ModelClient(object):
    """Abstract client. Subclasses implement ``complete``."""

    name = "abstract"

    def complete(self, request):
        """Run one request and return a ModelReply, or raise ModelError."""
        raise NotImplementedError
