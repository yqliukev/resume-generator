import customtkinter as ctk
from .app import App

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

def main() -> None:
    App().mainloop()

if __name__ == "__main__":
    main()