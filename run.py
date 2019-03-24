import bot
import credentials

#==================================================================================================================================================

bridget = bot.Bot(initial_extensions=["admin", "otogi", "bridget"], save_cookies="cookies.pkl")
if __name__ == "__main__":
    bridget.run(credentials.username, credentials.password, load_cookies="cookies.pkl")
