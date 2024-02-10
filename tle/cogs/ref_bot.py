import hashlib
import json
import requests
from discord.ext import commands
from tle.util import discord_common
import aiohttp
import logging
from tle.util import codeforces_common as cf_common
from tle import constants

logger = logging.getLogger(__name__)
RATING_LIMIT = 1500

class ReferralBotCogError(commands.CommandError):
    pass

class ReferralBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.url = "https://ref-portal-indol.vercel.app/api/secret?cfUserName=vedantmishra69&discordId=vedantmishra69"
        self.ref_channel_id = 0
        self.converter = commands.MemberConverter()
    
    def get_url(self, cf_handle, discord_id):
        """
        Prepares the URL with cf handle and discord id.
        """
        return f"https://ref-portal-indol.vercel.app/api/secret?cfUserName={cf_handle}&discordId={discord_id}"
    
    @commands.group(brief='Referral bot',
                    invoke_without_command=True)
    @cf_common.user_guard(group='ref')
    async def ref(self,ctx,*args):
        """
        Submits request for referral on ref portal.
        """
        await ctx.send_help(ctx.command)
    
    @ref.command(brief='sets channel for referral request.')
    @commands.has_any_role(constants.TLE_ADMIN, constants.TLE_MODERATOR)    
    async def set_channel(self,ctx):
        """
        Sets channel to be used for requesting referral form.
        """
        self.ref_channel_id = ctx.channel.id
        await ctx.send(embed=discord_common.embed_success('Referral channel saved successfully'))
    
    @ref.command(brief='requests referral form.')
    @cf_common.user_guard(group='ref')
    async def get(self, ctx):
        """
        Requests referral form from the ref portal.
        """
        if not self.ref_channel_id:
            raise ReferralBotCogError('There is no referral channel. Set one with ``;ref set_channel``.')
        if ctx.channel.id != self.ref_channel_id: 
            raise ReferralBotCogError(f"use it in <#{self.ref_channel_id}>")
        cf_handle, = await cf_common.resolve_handles(ctx, self.converter, ('!' + str(ctx.author.id),))
        discord_id = ctx.author.name
        url = self.get_url(cf_handle, discord_id)
        user = cf_common.user_db.fetch_cf_user(cf_handle)
        if user.maxRating < RATING_LIMIT:
            await ctx.reply(embed=discord_common.embed_alert(f"You need to have your maximum codeforces rating >= {RATING_LIMIT}."))
        else:
            dm_channel = await ctx.author.create_dm()
            payload = {
                "secretKey": "6QGMP4QD8amDPnTBC3Tfwo8L4Ckny4Cl",
                "secretAccessKey": "M4MICU67LFq5UH2NLaLSgbOaRBjliuO5"
            }
            try:
                response = json.loads(requests.get(url, headers=payload).text)
                if "url" in response:
                    res = response["url"]
                    await dm_channel.send(embed=discord_common.embed_success(f"Here is your referral form link: {res}\n\nPlease note that entering an **invalid job id** may result in your **banishment** from the server."))
                    await ctx.reply(embed=discord_common.embed_success("Sent!"))
                else: await dm_channel.send(embed=discord_common.embed_alert("No URL available."))
            except Exception as e:
                ctx.reply(embed=discord_common.embed_alert("No response from the server."))
                logger.warn(e)
                
    @discord_common.send_error_if(ReferralBotCogError, cf_common.ResolveHandleError,
                                  cf_common.FilterError)
    async def cog_command_error(self, ctx, error):
        pass           
    
        

async def setup(bot):
    await bot.add_cog(ReferralBot(bot))
        