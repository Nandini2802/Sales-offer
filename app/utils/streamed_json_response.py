
import json


class StreamedResponseExtractor:
    """
    Extracts the response string from streaming JSON.

    Supports:
    - JSON properties in either order
    - Escaped quotes and backslashes
    - Unicode escape sequences
    - Arbitrary chunk boundaries

    Holds trailing whitespace until completion.
    """

    def __init__(self):
        self.buffer = ""
        self.emitted = ""
        self.finished = False

    def feed(self, chunk: str) -> str:
        if self.finished:
            return ""

        self.buffer += chunk

        # Find the top-level response property.
        try:
            value_start = self._find_response_start()
        except ValueError:
            return ""

        if value_start is None:
            return ""

        # Decode as much of the JSON string as is complete.
        raw = self.buffer[value_start:]
        decoded, complete = self._decode_string_prefix(raw)

        # Avoid emitting whitespace that may be stripped
        # from the final response.
        safe = decoded if complete else decoded.rstrip()

        if not safe.startswith(self.emitted):
            raise ValueError(
                "Streaming text changed unexpectedly"
            )

        delta = safe[len(self.emitted):]
        self.emitted = safe

        if complete:
            self.finished = True

        return delta

    def _find_response_start(self):
        text = self.buffer
        decoder = json.JSONDecoder()

        pos = 0

        def skip_ws(index):
            while index < len(text) and text[index].isspace():
                index += 1
            return index

        pos = skip_ws(pos)

        if pos >= len(text) or text[pos] != "{":
            return None

        pos += 1

        while True:
            pos = skip_ws(pos)

            if pos >= len(text):
                return None

            if text[pos] == "}":
                return None

            try:
                key, consumed = decoder.raw_decode(text[pos:])
            except json.JSONDecodeError:
                return None

            if not isinstance(key, str):
                raise ValueError("Invalid JSON property")

            pos += consumed
            pos = skip_ws(pos)

            if pos >= len(text):
                return None

            if text[pos] != ":":
                raise ValueError("Invalid JSON separator")

            pos += 1
            pos = skip_ws(pos)

            if key == "response":
                if pos >= len(text):
                    return None

                if text[pos] != '"':
                    raise ValueError(
                        "Response must be a JSON string"
                    )

                return pos

            # Skip other completed JSON properties.
            try:
                _, consumed = decoder.raw_decode(text[pos:])
            except json.JSONDecodeError:
                return None

            pos += consumed
            pos = skip_ws(pos)

            if pos >= len(text):
                return None

            if text[pos] == ",":
                pos += 1
                continue

            if text[pos] == "}":
                return None

            raise ValueError("Invalid JSON object")

    @staticmethod
    def _decode_string_prefix(raw):
        if not raw.startswith('"'):
            return "", False

        escaped = False
        index = 1

        while index < len(raw):
            char = raw[index]

            if escaped:
                escaped = False
                index += 1
                continue

            if char == "\\":
                escaped = True
                index += 1
                continue

            if char == '"':
                try:
                    return json.loads(raw[:index + 1]), True
                except json.JSONDecodeError:
                    return "", False

            index += 1

        # Decode the largest valid string prefix.
        candidate = raw[1:]

        while candidate:
            try:
                decoded = json.loads(
                    '"' + candidate + '"'
                )

                # Avoid emitting an unmatched surrogate.
                if decoded and (
                    0xD800 <= ord(decoded[-1]) <= 0xDBFF
                ):
                    decoded = decoded[:-1]

                return decoded, False

            except json.JSONDecodeError:
                candidate = candidate[:-1]

        return "", False
