import sys

from src.core.nel import Nel
from src.core.runtime import create_runtime_nel
from src.errors import ApplicationError, PersistenceStartupError


for stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8")


def run():
    nel = None

    try:
        try:
            nel = create_runtime_nel(nel_factory=Nel)
        except (ApplicationError, PersistenceStartupError) as exc:
            print(f"Nel: {exc}", file=sys.stderr)
            return 1

        while True:
            text = input("Sən: ")

            if text == "exit":
                break

            try:
                response = nel.think(text)
                if response:
                    print(response)
            except ApplicationError as exc:
                print(f"Nel: {exc}")
    finally:
        if nel is not None:
            nel.stop()

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
