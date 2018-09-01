import bot
import credentials

#==================================================================================================================================================

bridget = bot.Bot(initial_extensions=["admin", "otogi", "bridget"])
if __name__ == "__main__":
    bridget.run(credentials.username, credentials.password)
