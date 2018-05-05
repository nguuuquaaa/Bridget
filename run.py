import bot
import credentials

#==================================================================================================================================================

bridget = bot.Bot(credentials.username, credentials.password, initial_extensions=["admin", "otogi", "bridget"])
if __name__ == "__main__":
    bridget.listen()
