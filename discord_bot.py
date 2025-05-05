import asyncio
import sqlite3
import os
import configparser
import hikari
import lightbulb
import lightbulb.commands
import lightbulb.context
import miru
from google import genai
from datetime import datetime
from poll_api import StrawpollAPI

if os.name != "nt":
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

workpath = os.path.dirname(__file__)
#read config
config = configparser.RawConfigParser()
config.sections()
config.read(os.path.join(workpath, "config.ini"))
gemini_token = config['GEMINI']['token']
gemini_client = genai.Client(api_key=gemini_token)
discord_token = config['DISCORD']['token']
#start sql connection
sqlite_conn = sqlite3.connect(os.path.join(workpath, "fumochan.db"))
sql_cursor = sqlite_conn.cursor()
#create sql tables
sql_cursor.execute("CREATE TABLE IF NOT EXISTS guilds (id INTEGER PRIMARY KEY, name TEXT, notifications_enabled INTEGER, notifications_channel_id INTEGER)")
sql_cursor.execute("CREATE TABLE IF NOT EXISTS channels (id INTEGER PRIMARY KEY, name TEXT, guild_id INTEGER, FOREIGN KEY (guild_id) REFERENCES guilds(id))")
sql_cursor.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER, name TEXT, guild_id INTEGER, FOREIGN KEY (guild_id) REFERENCES guilds(id), PRIMARY KEY (id, guild_id))")
sql_cursor.execute("CREATE TABLE IF NOT EXISTS messages (id INTEGER, timestamp TEXT, content TEXT, user_id INTEGER, channel_id INTEGER, guild_id INTEGER, FOREIGN KEY (guild_id) REFERENCES guilds(id), FOREIGN KEY (user_id) REFERENCES users(id), FOREIGN KEY (channel_id) REFERENCES channels(id))")
sqlite_conn.commit()

#create bot
discord_bot = hikari.GatewayBot(token=discord_token,intents=hikari.Intents.ALL)
lightbulb_client = lightbulb.client_from_app(discord_bot)
miru_client = miru.Client(discord_bot)
discord_bot.subscribe(hikari.StartingEvent, lightbulb_client.start)

@discord_bot.listen()
async def store_message(event: hikari.GuildMessageCreateEvent) -> None:
    """Store received messages into db"""

    #Only store human messages
    #if not event.is_human:
    #    return

    if event.message.content:
        sql_cursor.execute(f'REPLACE INTO guilds(id) VALUES({event.message.guild_id})')
        sql_cursor.execute(f'REPLACE INTO channels(id) VALUES({event.message.channel_id})')
        sql_cursor.execute(f'REPLACE INTO users(id, name, guild_id) VALUES({event.message.author.id}, "{event.message.author.display_name}", {event.message.guild_id})')
        sql_cursor.execute(f'INSERT INTO messages(id, timestamp, user_id, channel_id, guild_id, content) VALUES({event.message.id}, "{event.message.timestamp}", {event.message.author.id}, {event.message.channel_id}, {event.message.guild_id}, "{event.message.content}")')
        sqlite_conn.commit()

        me = discord_bot.get_me()
        if me.id in event.message.user_mentions_ids:
            if event.message.channel_id != 1342486090472362026:
                sql_cursor.execute(f'SELECT DISTINCT channel_id FROM messages WHERE messages.guild_id=({event.message.guild_id})')
                channels = sql_cursor.fetchall()
                sql_cursor.execute(f'SELECT users.name,channel_id,timestamp,content,messages.id FROM messages INNER JOIN users ON messages.user_id=users.id WHERE messages.guild_id=({event.message.guild_id}) ORDER BY messages.id DESC LIMIT 6000')
                messages = sql_cursor.fetchall()
                guild = discord_bot.cache.get_guild(event.message.guild_id)
                summary = ""
                for channel in channels:
                    channel_name = guild.get_channel(channel[0])
                    summary += f"\n\nChannel: {channel_name}"
                    for message in messages:
                        if message[0] != "Fumo-chan":
                            if message[1] == channel[0]:
                                summary += f"\n{datetime.strptime(message[2][:19], '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d %H:%M')}, {message[0]}: {message[3]}"
                response = gemini_client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=f'{event.message.author.display_name} fragt dich folgendes:{event.message.content}.\nAntworte dem User menschlich. Hier ist als Kontext noch der Chatverlauf nach Channeln sortiert mit Zeitstempeln:\n{summary}',
                )
                if len(response.text) < 1990:
                    await event.message.respond(response.text)
                else:
                    blocks = []
                    current_block = ""
                    lines = response.text.splitlines(keepends=True) 

                    for line in lines:
                        if len(current_block) + len(line) < 1990:
                            current_block += line
                        else:
                            if current_block:  
                                blocks.append(current_block)
                            current_block = line

                    if current_block:
                        blocks.append(current_block)  

                    for block in blocks:
                        await event.message.respond(block)


@lightbulb_client.register()
class EnableNotifications(
    lightbulb.SlashCommand,
    name="enable-notifications",
    dm_enabled=False,
    default_member_permissions=hikari.Permissions.ADMINISTRATOR,
    description="Enables Fumotel Bot Guild notifications",
):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        await ctx.defer(ephemeral=True)
        sql_cursor.execute(f'INSERT OR IGNORE INTO guilds(id) VALUES({ctx.guild_id})')
        sql_cursor.execute(f'UPDATE guilds SET notifications_enabled = 1 WHERE id = {ctx.guild_id}')
        sqlite_conn.commit()
        await ctx.respond("Notifications enabled!", ephemeral=True)

@lightbulb_client.register()
class DisableNotifications(
    lightbulb.SlashCommand,
    name="disable-notifications",
    dm_enabled=False,
    default_member_permissions=hikari.Permissions.ADMINISTRATOR,
    description="Disables Fumotel Bot Guild notifications",
):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        await ctx.defer(ephemeral=True)
        sql_cursor.execute(f'INSERT OR IGNORE INTO guilds(id) VALUES({ctx.guild_id})')
        sql_cursor.execute(f'UPDATE guilds SET notifications_enabled = 0 WHERE id = {ctx.guild_id}')
        sqlite_conn.commit()
        await ctx.respond("Notifications disabled!", ephemeral=True)

@lightbulb_client.register()
class SetChannel(
    lightbulb.SlashCommand,
    name="set-notification-channel",
    dm_enabled=False,
    default_member_permissions=hikari.Permissions.ADMINISTRATOR,
    description="Sets current channel as notification channel"
):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        await ctx.defer(ephemeral=True)
        sql_cursor.execute(f'INSERT OR IGNORE INTO guilds(id) VALUES({ctx.guild_id})')
        sql_cursor.execute(f'INSERT OR IGNORE INTO channels(id) VALUES({ctx.channel_id})')
        sql_cursor.execute(f'UPDATE guilds SET notifications_channel_id = {ctx.channel_id} WHERE id = {ctx.guild_id}')
        sqlite_conn.commit()
        await ctx.respond("Channel set!", ephemeral=True)


@lightbulb_client.register()
class CreatePollCommand(
    lightbulb.SlashCommand,
    name = "create-poll",
    description = "Erstellt eine Umfrage"
):
    @lightbulb.Option("duration", "Dauer in Minuten", type = int)
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        await discord_bot.request_guild_members(ctx.guild_id, query = "", limit = 0)

        members = [m for m in discord_bot.cache.get_members_view_for_guild(ctx.guild_id).values() if not m.is_bot]
        names = [m.username for m in members]
        duration = ctx.command._resolve_option(duration)
        poll = StrawpollAPI

        try:
            poll_data = poll.create_poll("Wer soll als nächstes gebannt werden", names, duration)
            poll_url = poll.get_poll_url(poll_data)
            await ctx.respond(f"poll created: {poll_url}")

        except Exception as e:
            await ctx.respond(f"poll creation failed: {e}")

if __name__ == "__main__":
    discord_bot.run()
