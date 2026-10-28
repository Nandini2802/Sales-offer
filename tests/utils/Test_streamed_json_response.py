
from app.utils.streamed_json_response import (
    StreamedResponseExtractor,
)


def run_test(name, raw_json, expected):
    extractor = StreamedResponseExtractor()
    received = ""

    # Send one character at a time.
    # This tests arbitrary chunk boundaries.
    for character in raw_json:
        received += extractor.feed(character)

    assert received == expected, (
        f"{name}: Expected {expected!r}, "
        f"received {received!r}"
    )

    assert extractor.finished, (
        f"{name}: Response string was not completed"
    )

    print(f"PASS: {name}")


def main():
    run_test(
        "English",
        '{"response":"Hello, welcome to Danube!",'
        '"followups":[]}',
        "Hello, welcome to Danube!",
    )

    run_test(
        "Followups before response",
        '{"followups":["Show brochure"],'
        '"response":"Project details"}',
        "Project details",
    )

    run_test(
        "Escaped quotation marks",
        '{"response":"He said \\"Hello\\".",'
        '"followups":[]}',
        'He said "Hello".',
    )

    run_test(
        "Newline",
        '{"response":"First line\\nSecond line",'
        '"followups":[]}',
        "First line\nSecond line",
    )

    run_test(
        "Arabic",
        '{"response":"مرحبا بكم في دبي",'
        '"followups":[]}',
        "مرحبا بكم في دبي",
    )

    run_test(
        "Unicode escape",
        '{"response":"Dubai \\u2764",'
        '"followups":[]}',
        "Dubai ❤",
    )

    run_test(
        "Emoji surrogate pair",
        '{"response":"Welcome \\ud83d\\ude0a",'
        '"followups":[]}',
        "Welcome 😊",
    )

    run_test(
        "Trailing whitespace",
        '{"response":"Hello world   ",'
        '"followups":[]}',
        "Hello world   ",
    )

    print("\nAll extractor tests passed.")


if __name__ == "__main__":
    main()
