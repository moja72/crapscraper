from app.bootstrap import create_application


def main() -> None:
    create_application().serve()


if __name__ == "__main__":
    main()
