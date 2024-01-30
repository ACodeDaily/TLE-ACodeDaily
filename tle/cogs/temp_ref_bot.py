import hashlib
import json
import requests
from discord.ext import commands
import aiohttp
from tle.util import codeforces_common as cf_common


class RefferalBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.url = "https://ref-portal-indol.vercel.app/api/secret?cfUserName=vedantmishra69&discordId=vedantmishra69"
    
    def get_url(self, cf_handle, discord_id):
        return f"https://ref-portal-indol.vercel.app/api/secret?cfUserName={cf_handle}&discordId={discord_id}"
    
    # def get_token(self, handle):
    #     hash_object = hashlib.sha256()
    #     encoded_data = handle.encode()
    #     hash_object.update(encoded_data)
    #     hash_digest = hash_object.hexdigest()
    #     return hash_digest
    
    # async def fetch(self, url, headers):
    #     async with aiohttp.ClientSession() as session:
    #         async with session.get(url, headers=headers) as response:
    #             return await response.text()
    
    @commands.command(brief="Sends refferal request.")
    async def getref(self, ctx):
        cf_handle = cf_common.user_db.get_handle(ctx.author.id, ctx.guild.id)
        discord_id = ctx.author.name
        url = self.get_url(cf_handle, discord_id)
        user = cf_common.user_db.fetch_cf_user(cf_handle)
        dm_channel = await ctx.author.create_dm()
        if user.effective_rating < 100:
            await dm_channel.send("You need to expert or above to apply for refferal.")
        else:
            try:
                payload = {
                    "secretKey": "6QGMP4QD8amDPnTBC3Tfwo8L4Ckny4Cl",
                    "secretAccessKey": "M4MICU67LFq5UH2NLaLSgbOaRBjliuO5"
                }
                response = json.loads(requests.get(url, headers=payload).text)
                if "url" in response:
                    res = response["url"]
                    await dm_channel.send(f"{res}")
                else: await dm_channel.send("NO")
            except Exception as e:
                print(e)
        

async def setup(bot):
    await bot.add_cog(RefferalBot(bot))
        