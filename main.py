from src.core.nel import Nel

nel = Nel()

while True:

    text = input("Sən: ")

    if text == "exit":
        break

    if text.startswith("/remember "):
        nel.remember(text[10:])
        print("Yadda saxladım.")
        continue

    print(nel.think(text))