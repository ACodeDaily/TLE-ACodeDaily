from discord.ext import commands
import logging
import google.generativeai as genai
from tle.util import gemini_model_settings as settings
from tle.util import discord_common
from tle.util import codeforces_common as cf_common
import requests
from PIL import Image
from tle import constants
from ratelimit import limits, sleep_and_retry



ONE_MINUTE = 60
MAX_CALLS_PER_MINUTE = 60
GEMINI_API_KEY = constants.GEMINI_API_KEY

IMAGE_TYPES = ["jpeg", "png", "webp", "heic", "heif"]
NO_RESPONSE_MESSAGE = "Sorry, can't answer that. possible reasons might be no response, recitation, safety issue or blocked content. if you are getting this message multiple times, make a separate chat/private thread."
DEV_ID = 501026469569363988
logger = logging.getLogger(__name__)

class ACD_AI_COG_ERROR(commands.CommandError):
    pass

class ACD_AI(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        '''developer's discord user id (vedantmishra69)'''
        self.dev_id: int = DEV_ID
        
        genai.configure(api_key=GEMINI_API_KEY)
        
        '''gemini model for text inputs'''
        self.text_model = genai.GenerativeModel(model_name="gemini-pro",
                              generation_config=settings.text_generation_config, 
                              safety_settings=settings.text_safety_settings)
        
        '''gemini model for image inputs'''
        self.image_model = genai.GenerativeModel(model_name="gemini-pro-vision",
                              generation_config=settings.image_generation_config, 
                              safety_settings=settings.image_safety_settings)
        
        '''to store chat session instances for each opened thread (thread_id: chat_session)'''
        self.chats: dict = {}
        
    @commands.Cog.listener()
    async def on_ready(self):
        '''to delete existing threads when the bot wakes up'''
        await self.delete_threads_on_start()

    @commands.group(brief='AI Chat Bot',
                    invoke_without_command=True)
    @cf_common.user_guard(group='ai')
    async def ai(self,ctx,*args):
        '''
        AI chat powered by Google's Gemini Pro.
        it responds to both text and image inputs, 
        feel free to drop code snippets as well.
        '''
        await ctx.send_help(ctx.command)
        
    async def delete_threads(self, channel_id):
        '''deletes thread for the given channel'''
        try:
            channel = await self.bot.fetch_channel(channel_id)
            for thread in channel.threads:
                if thread.owner.id == self.bot.user.id:
                    await thread.delete()
                    if thread.id in self.chats: self.chats.pop(thread.id)
        except Exception as e:
            logger.warn(f"Couldn't delete threads for {channel_id}: {e}")
            
    async def delete_threads_on_start(self):
        '''deletes existing threads when the bot wakes up'''
        try:
            async for guild in self.bot.fetch_guilds():
                channel_id = cf_common.user_db.get_ai_channel(guild.id)
                if channel_id: await self.delete_threads(channel_id)
        except Exception as e:
            logger.warn(f"Couldn't fetch guilds\n{e}")
            
    def check_channel(self, ctx):
        '''checks if a channel has been set and the current channel is the set one or not'''
        channel_id = cf_common.user_db.get_ai_channel(ctx.guild.id)
        if not channel_id:
            raise ACD_AI_COG_ERROR('There is no ai channel. Set one with ``;ai set_channel``.')
        if ctx.channel.id != channel_id:
            raise ACD_AI_COG_ERROR(f"You must use this command in ai channel: <#{channel_id}>")
        
    async def print_response(self, response, message):
        '''prints the response to thread channel recieved from get_response()'''
        async with message.channel.typing():
            strings = []
            for index in range(0, len(response), 2000):
                strings.append(response[index: min(len(response), index + 2000)])
            try:
                await message.reply(strings[0])
                for string in strings[1:]:
                    await message.channel.send(string)
            except Exception as e:
                message.reply("No response, discord issue :(")
                logger.warn(f"last message: {message.content}\n{e}")
    
    @sleep_and_retry
    @limits(calls=MAX_CALLS_PER_MINUTE, period=ONE_MINUTE)
    async def get_response(self, message, chat):
        '''
        takes message object and chat session instance
        sends the message content (text/image) to gemini model
        sends the response recieved from gemini to print_response()
        '''
        async with message.channel.typing():
            image = None
            response = NO_RESPONSE_MESSAGE
            attachment = message.attachments[0] if message.attachments else None
            if not attachment:
                try:
                    response = chat.send_message(message.content).text
                    if not isinstance(response, str):
                            raise Exception
                except Exception as e:
                    logger.warn(f"last message: {message.content}\n{e}".format())
            elif attachment.content_type.split('/')[0] == "image":
                if attachment.content_type.split('/')[1] in IMAGE_TYPES:
                    try:
                        image = Image.open(requests.get(attachment.url, stream = True).raw)
                        response = self.image_model.generate_content([message.content, image] if message.content else image).text
                        if not isinstance(response, str):
                            raise Exception
                    except Exception as e:
                        response = "Unable to process that image."
                        logger.warn(f"last message: {attachment.url}\n{e}".format())
                else: response = "Invalid image format. please use JPEG, PNG, WEBP, HEIC or HEIF"
            else: response = "Attachment not supported."
        self.bot.loop.create_task(self.print_response(response, message))
    
    async def start_thread(self, message, is_public):
        '''starts a thread on ;ai chat or ;ai private commands'''
        try:
            thread = await message.channel.create_thread(name = f"Session with {message.author.name}", slowmode_delay = 1, auto_archive_duration = 60, message = message if is_public else None)
            await thread.add_user(message.author)
            hello_text = self.text_model.generate_content("hi").text
            async with thread.typing():
                await thread.send(content = f'<@{message.author.id}> {hello_text}')
            self.chats[str(thread.id)] = self.text_model.start_chat(history=[{'role':'user', 'parts': ["hi"]}, {'role': 'model', 'parts': [hello_text]}])
        except Exception as e:
            await message.channel.send(embed=discord_common.embed_alert("Could not start a thread."))
            logger.warn(e)
            
    @ai.command(brief='gets channel for ai.')
    async def get_channel(self, ctx):
        '''gets channel to be used for ai.'''
        channel_id = cf_common.user_db.get_ai_channel(ctx.guild.id)
        if not channel_id:
            raise ACD_AI_COG_ERROR('There is no ai channel. Set one with ``;ai set_channel``.')
        await ctx.send(embed=discord_common.embed_success(f"Current ai channel: <#{channel_id}>"))
    
    @ai.command(brief='sets channel for ai.')
    @commands.has_any_role(constants.TLE_ADMIN, constants.TLE_MODERATOR)    
    async def set_channel(self, ctx):
        '''sets channel to be used for ai.'''
        channel_id = cf_common.user_db.get_ai_channel(ctx.guild.id)
        if channel_id: await self.delete_threads(channel_id)
        cf_common.user_db.set_ai_channel(ctx.guild.id, ctx.channel.id)
        await ctx.send(embed=discord_common.embed_success('AI channel saved successfully'))

    @ai.command(brief='deletes all active chat threads.')
    @commands.has_any_role(constants.TLE_ADMIN, constants.TLE_MODERATOR)
    async def clear(self, ctx):
        '''deletes all active chat and private threads'''
        self.check_channel(ctx)
        async with ctx.channel.typing():
            await self.delete_threads(ctx.channel.id)
        await ctx.send(embed=discord_common.embed_success(f"All threads deleted for ``{ctx.channel.name}``."))

    @commands.Cog.listener()
    async def on_message(self, message):
        '''sends user's input for processing to gemini'''
        if str(message.channel.id) in self.chats and message.author != self.bot.user:
            self.bot.loop.create_task(self.get_response(message, self.chats[str(message.channel.id)]))
        
    @ai.command(brief='creates a public chat thread.')
    async def chat(self, ctx):    
        self.check_channel(ctx)
        await self.start_thread(ctx.message, True)
            
    @ai.command(brief='creates a private chat thread.')
    async def private(self, ctx):    
        self.check_channel(ctx)
        await self.start_thread(ctx.message, False)
            
    @discord_common.send_error_if(ACD_AI_COG_ERROR, cf_common.ResolveHandleError,
                                  cf_common.FilterError)
    async def cog_command_error(self, ctx, error):
        pass

async def setup(bot):
    await bot.add_cog(ACD_AI(bot))