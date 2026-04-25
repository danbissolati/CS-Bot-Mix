import discord
from discord.ext import commands
import random
import os
import json

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ─── State — dict {user: gc_level_str} ───────────────────────────────────────
players: dict = {}      # mix 1
mix2_players: dict = {} # mix 2
mix3_players: list = [] # mix 3 — no level needed
mix_test_players: list = [] # mix test — allows same player twice, max 2

# ─── Password ────────────────────────────────────────────────────────────────
CLEAN_RANK_PASSWORD = "Hahaha123"

# ─── Stats file ──────────────────────────────────────────────────────────────
STATS_FILE = os.path.join(os.path.dirname(__file__), "stats.json")


def load_stats() -> dict:
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_stats(stats: dict):
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)


def record_result(winners: list, losers: list):
    """Add 1 win to each winner and 1 loss to each loser."""
    stats = load_stats()
    for p in winners:
        uid = str(p.id)
        if uid not in stats:
            stats[uid] = {"name": p.display_name, "wins": 0, "losses": 0}
        stats[uid]["wins"] += 1
        stats[uid]["name"] = p.display_name
    for p in losers:
        uid = str(p.id)
        if uid not in stats:
            stats[uid] = {"name": p.display_name, "wins": 0, "losses": 0}
        stats[uid]["losses"] += 1
        stats[uid]["name"] = p.display_name
    save_stats(stats)


# ══════════════════════════════════════════════════════════════════════════════
#  Winner declaration view
# ══════════════════════════════════════════════════════════════════════════════

class WinnerView(discord.ui.View):
    """
    Sent after teams are defined.
    Any of the 10 match players can declare the winner once.
    """

    def __init__(self, team1: list, team2: list, label1: str = "🟦 Time 1", label2: str = "🟥 Time 2"):
        super().__init__(timeout=None)
        self.team1 = team1          # list of discord.Member
        self.team2 = team2
        self.label1 = label1
        self.label2 = label2
        self.all_players = set(p.id for p in team1 + team2)
        self.declared = False

    async def _declare(self, interaction: discord.Interaction, winners: list, losers: list, winner_label: str):
        if self.declared:
            await interaction.response.send_message("O resultado já foi declarado!", ephemeral=True)
            return

        if interaction.user.id not in self.all_players:
            await interaction.response.send_message(
                "⛔ Apenas os jogadores da partida podem declarar o vencedor.", ephemeral=True
            )
            return

        self.declared = True
        record_result(winners, losers)

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(
            content=f"🏆 **{winner_label} venceu!** Resultado registrado no ranking.",
            view=self,
        )

        winner_names = ", ".join(p.display_name for p in winners)
        await interaction.channel.send(
            f"🎉 **{winner_label}** ganhou!\n"
            f"Vitória registrada para: {winner_names}\n"
            f"Use `!rank` para ver o ranking de vitórias."
        )

    @discord.ui.button(label="Time 1", style=discord.ButtonStyle.blurple)
    async def team1_wins(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._declare(interaction, self.team1, self.team2, self.label1)

    @discord.ui.button(label="Time 2", style=discord.ButtonStyle.red)
    async def team2_wins(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._declare(interaction, self.team2, self.team1, self.label2)


async def send_winner_vote(channel, team1: list, team2: list, label1="🟦 Time 1", label2="🟥 Time 2"):
    """Send the winner declaration message after a match."""
    view = WinnerView(team1, team2, label1, label2)
    await channel.send(
        "⚔️ **Quem ganhou a partida?** Um dos jogadores deve declarar o vencedor:",
        view=view,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════════════

def balanced_teams(players_with_levels: dict):
    sorted_players = sorted(
        players_with_levels.items(),
        key=lambda x: int(x[1]),
        reverse=True,
    )
    team1, team2 = [], []
    pattern = [1, 2, 2, 1, 1, 2, 2, 1, 1, 2]
    for i, (player, level) in enumerate(sorted_players):
        if pattern[i] == 1:
            team1.append((player, level))
        else:
            team2.append((player, level))
    return team1, team2


def format_teams_message(team1, team2):
    t1_total = sum(int(lvl) for _, lvl in team1)
    t2_total = sum(int(lvl) for _, lvl in team2)

    msg = "**🔥 TIMES DEFINIDOS 🔥**\n\n"
    msg += f"**🟦 Time 1** *(média: {t1_total / len(team1):.1f})*:\n"
    for p, lvl in team1:
        msg += f"- {p.mention} *(Nível {lvl})*\n"
    msg += f"\n**🟥 Time 2** *(média: {t2_total / len(team2):.1f})*:\n"
    for p, lvl in team2:
        msg += f"- {p.mention} *(Nível {lvl})*\n"
    return msg


# ══════════════════════════════════════════════════════════════════════════════
#  MIX 1 — balanced teams by GC level
# ══════════════════════════════════════════════════════════════════════════════

class Mix1GCModal(discord.ui.Modal, title="Nível na GC"):
    gc_level = discord.ui.TextInput(
        label="Qual é o seu nível na GC?",
        placeholder="Digite um número de 1 a 21",
        min_length=1,
        max_length=2,
    )

    def __init__(self, channel):
        super().__init__()
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        user = interaction.user
        level = self.gc_level.value.strip()

        if not level.isdigit() or not (1 <= int(level) <= 21):
            await interaction.response.send_message(
                "❌ Nível inválido! Digite um número entre **1** e **21**.", ephemeral=True
            )
            return

        if user in players:
            await interaction.response.send_message("Você já entrou!", ephemeral=True)
            return

        players[user] = level
        count = len(players)

        await interaction.response.send_message(
            f"✅ Você entrou no mix com nível **{level}**! ({count}/10)", ephemeral=True
        )
        await self.channel.send(
            f"👤 **{user.display_name}** entrou! Nível: **{level}** ({count}/10)"
        )

        if count == 10:
            team1, team2 = balanced_teams(dict(players))
            await self.channel.send(format_teams_message(team1, team2))
            t1_users = [p for p, _ in team1]
            t2_users = [p for p, _ in team2]
            players.clear()
            await send_winner_vote(self.channel, t1_users, t2_users)


class MixView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        if user in players:
            await interaction.response.send_message("Você já entrou!", ephemeral=True)
            return
        modal = Mix1GCModal(channel=interaction.channel)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.red)
    async def recuse(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user in players:
            del players[interaction.user]
            await interaction.response.send_message("❌ Você saiu do mix.", ephemeral=True)
        else:
            await interaction.response.send_message("Você não está na fila.", ephemeral=True)


# ══════════════════════════════════════════════════════════════════════════════
#  MIX 2 — captain draft with GC level
# ══════════════════════════════════════════════════════════════════════════════

class Mix2GCModal(discord.ui.Modal, title="Nível na GC"):
    gc_level = discord.ui.TextInput(
        label="Qual é o seu nível na GC?",
        placeholder="Digite um número de 1 a 21",
        min_length=1,
        max_length=2,
    )

    def __init__(self, channel):
        super().__init__()
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        user = interaction.user
        level = self.gc_level.value.strip()

        if not level.isdigit() or not (1 <= int(level) <= 21):
            await interaction.response.send_message(
                "❌ Nível inválido! Digite um número entre **1** e **21**.", ephemeral=True
            )
            return

        if user in mix2_players:
            await interaction.response.send_message("Você já entrou!", ephemeral=True)
            return

        mix2_players[user] = level
        count = len(mix2_players)

        await interaction.response.send_message(
            f"✅ Você entrou no mix2 com nível **{level}**! ({count}/10)", ephemeral=True
        )
        await self.channel.send(
            f"👤 **{user.display_name}** entrou! Nível: **{level}** ({count}/10)"
        )

        if count == 10:
            session = DraftSession(dict(mix2_players))
            c0, c1 = session.captains

            await self.channel.send(
                f"👑 **CAPITÃES DEFINIDOS!**\n"
                f"🟦 **{c0.mention}** (Nível: {session.levels[c0]}) "
                f"vs 🟥 **{c1.mention}** (Nível: {session.levels[c1]})\n\n"
                f"Cada capitão escolhe 1 jogador por vez, alternando."
            )

            view = DraftView(session, self.channel)
            await self.channel.send(
                f"🎯 Vez de **{c0.mention}** escolher primeiro:",
                view=view,
            )


class DraftSession:
    def __init__(self, players_with_levels: dict):
        all_players = list(players_with_levels.keys())
        random.shuffle(all_players)
        self.levels = players_with_levels
        self.captains = all_players[:2]
        self.remaining = all_players[2:]
        self.teams = {
            self.captains[0]: [self.captains[0]],
            self.captains[1]: [self.captains[1]],
        }
        self.turn = 0

    def current_captain(self):
        return self.captains[self.turn]

    def pick(self, player):
        captain = self.current_captain()
        self.teams[captain].append(player)
        self.remaining.remove(player)
        self.turn = 1 - self.turn

    def is_done(self):
        return len(self.remaining) == 0

    def final_message(self):
        c0, c1 = self.captains

        def team_avg(captain):
            lvls = [int(self.levels[p]) for p in self.teams[captain]]
            return sum(lvls) / len(lvls)

        msg = "**🏆 TIMES DEFINIDOS 🏆**\n\n"
        msg += f"**🟦 Time de {c0.display_name}** *(média: {team_avg(c0):.1f})*:\n"
        for p in self.teams[c0]:
            msg += f"- {p.mention} *(Nível: {self.levels[p]})*\n"
        msg += f"\n**🟥 Time de {c1.display_name}** *(média: {team_avg(c1):.1f})*:\n"
        for p in self.teams[c1]:
            msg += f"- {p.mention} *(Nível: {self.levels[p]})*\n"
        return msg


class DraftView(discord.ui.View):
    def __init__(self, session: DraftSession, channel):
        super().__init__(timeout=None)
        self.session = session
        self.channel = channel
        self._build_buttons()

    def _build_buttons(self):
        self.clear_items()
        for player in self.session.remaining:
            level = self.session.levels[player]
            btn = discord.ui.Button(
                label=f"{player.display_name} [Nível {level}]",
                style=discord.ButtonStyle.primary,
                custom_id=f"draft_{player.id}",
            )
            btn.callback = self._make_callback(player)
            self.add_item(btn)

    def _make_callback(self, player):
        async def callback(interaction: discord.Interaction):
            session = self.session
            captain = session.current_captain()

            if interaction.user != captain:
                await interaction.response.send_message(
                    f"⛔ Não é sua vez! Aguarde **{captain.display_name}** escolher.",
                    ephemeral=True,
                )
                return

            session.pick(player)

            if session.is_done():
                for item in self.children:
                    item.disabled = True
                await interaction.response.edit_message(
                    content="✅ **Todos os jogadores foram escolhidos!**",
                    view=self,
                )
                await interaction.channel.send(session.final_message())
                c0, c1 = session.captains
                t1 = session.teams[c0]
                t2 = session.teams[c1]
                mix2_players.clear()
                await send_winner_vote(
                    interaction.channel, t1, t2,
                    label1=f"🟦 Time de {c0.display_name}",
                    label2=f"🟥 Time de {c1.display_name}",
                )
            else:
                next_captain = session.current_captain()
                self._build_buttons()
                await interaction.response.edit_message(
                    content=(
                        f"🎯 **{captain.display_name}** escolheu **{player.display_name}**!\n\n"
                        f"👑 Vez de **{next_captain.mention}** escolher:"
                    ),
                    view=self,
                )

        return callback


class Mix2View(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        if user in mix2_players:
            await interaction.response.send_message("Você já entrou!", ephemeral=True)
            return
        modal = Mix2GCModal(channel=interaction.channel)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.red)
    async def recuse(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user in mix2_players:
            del mix2_players[interaction.user]
            await interaction.response.send_message("❌ Você saiu do mix2.", ephemeral=True)
        else:
            await interaction.response.send_message("Você não está na fila.", ephemeral=True)


# ══════════════════════════════════════════════════════════════════════════════
#  MIX 3 — random teams, no level required
# ══════════════════════════════════════════════════════════════════════════════

class Mix3View(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user

        if user in mix3_players:
            await interaction.response.send_message("Você já entrou!", ephemeral=True)
            return

        mix3_players.append(user)
        await interaction.response.send_message(
            f"✅ {user.name} entrou no mix3! ({len(mix3_players)}/10)", ephemeral=True
        )
        await interaction.channel.send(f"👤 **{user.display_name}** entrou! ({len(mix3_players)}/10)")

        if len(mix3_players) == 10:
            random.shuffle(mix3_players)
            team1 = mix3_players[:5]
            team2 = mix3_players[5:]

            msg = "**🔥 TIMES DEFINIDOS 🔥**\n\n"
            msg += "**🟦 Time 1:**\n"
            for p in team1:
                msg += f"- {p.mention}\n"
            msg += "\n**🟥 Time 2:**\n"
            for p in team2:
                msg += f"- {p.mention}\n"

            await interaction.channel.send(msg)
            t1 = list(team1)
            t2 = list(team2)
            mix3_players.clear()
            await send_winner_vote(interaction.channel, t1, t2)

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.red)
    async def recuse(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user in mix3_players:
            mix3_players.remove(interaction.user)
            await interaction.response.send_message("❌ Você saiu do mix3.", ephemeral=True)
        else:
            await interaction.response.send_message("Você não está na fila.", ephemeral=True)


# ══════════════════════════════════════════════════════════════════════════════
#  MIX TEST — 2 players max, same player can join twice, no level
# ══════════════════════════════════════════════════════════════════════════════

class MixTestPasswordModal(discord.ui.Modal, title="Senha do Mix Teste"):
    senha = discord.ui.TextInput(
        label="Digite a senha para entrar:",
        placeholder="Senha...",
        min_length=1,
        max_length=30,
    )

    def __init__(self, channel):
        super().__init__()
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        if self.senha.value != CLEAN_RANK_PASSWORD:
            await interaction.response.send_message(
                "❌ Senha incorreta! Você não pode entrar no mix de teste.", ephemeral=True
            )
            return

        if len(mix_test_players) >= 2:
            await interaction.response.send_message("O lobby já está cheio (2/2)!", ephemeral=True)
            return

        mix_test_players.append(interaction.user)
        count = len(mix_test_players)

        await interaction.response.send_message(
            f"✅ Você entrou no mix de teste! ({count}/2)", ephemeral=True
        )
        await self.channel.send(
            f"👤 **{interaction.user.display_name}** entrou! ({count}/2)"
        )

        if count == 2:
            team1 = [mix_test_players[0]]
            team2 = [mix_test_players[1]]

            msg = "**🧪 TESTE — TIMES DEFINIDOS**\n\n"
            msg += f"**🟦 Time 1:** {team1[0].mention}\n"
            msg += f"**🟥 Time 2:** {team2[0].mention}\n"

            await self.channel.send(msg)
            mix_test_players.clear()
            await send_winner_vote(self.channel, team1, team2)


class MixTestView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        if len(mix_test_players) >= 2:
            await interaction.response.send_message("O lobby já está cheio (2/2)!", ephemeral=True)
            return

        await interaction.response.send_modal(MixTestPasswordModal(channel=interaction.channel))

    @discord.ui.button(label="Sair", style=discord.ButtonStyle.red)
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user in mix_test_players:
            mix_test_players.remove(interaction.user)
            await interaction.response.send_message("❌ Você saiu do mix de teste.", ephemeral=True)
        else:
            await interaction.response.send_message("Você não está na fila.", ephemeral=True)


# ══════════════════════════════════════════════════════════════════════════════
#  CLEAN RANK — password-protected rank reset
# ══════════════════════════════════════════════════════════════════════════════

class CleanRankModal(discord.ui.Modal, title="Resetar Ranking"):
    senha = discord.ui.TextInput(
        label="Digite a senha para resetar o ranking:",
        placeholder="Senha...",
        min_length=1,
        max_length=30,
    )

    async def on_submit(self, interaction: discord.Interaction):
        if self.senha.value != CLEAN_RANK_PASSWORD:
            await interaction.response.send_message(
                "❌ Senha incorreta! O ranking não foi resetado.", ephemeral=True
            )
            return

        save_stats({})
        await interaction.response.send_message(
            "✅ **Ranking resetado com sucesso!** Todos os dados foram apagados.", ephemeral=True
        )
        await interaction.channel.send("🗑️ **O ranking foi resetado!** Novos jogos, nova história.")


# ══════════════════════════════════════════════════════════════════════════════
#  Events & Commands
# ══════════════════════════════════════════════════════════════════════════════

@bot.event
async def on_ready():
    print(f"✅ Bot conectado como {bot.user} (ID: {bot.user.id})")
    print("------")


@bot.command()
async def mix(ctx):
    """Inicia um mix com times equilibrados por nível GC."""
    players.clear()
    view = MixView()
    await ctx.send(
        "🎮 **MIX ABERTO! (Times Equilibrados)**\n"
        "Ao entrar, informe seu **nível na GC** (1-21).\n"
        "Os times serão montados de forma equilibrada com base nos níveis!\n\n"
        "Clique em **Entrar** para participar (0/10):",
        view=view,
    )


@bot.command(name="mix2")
async def mix2(ctx):
    """Inicia um mix com draft de capitães e nível GC."""
    mix2_players.clear()
    view = Mix2View()
    await ctx.send(
        "🎮 **MIX 2 ABERTO! (Modo Draft)**\n"
        "Ao entrar, você precisará informar o seu **nível na GC** (1-21).\n"
        "Quando 10 jogadores entrarem, 2 capitães serão sorteados e escolherão seus times!\n\n"
        "Clique em **Entrar** para participar (0/10):",
        view=view,
    )


@bot.command(name="mix3")
async def mix3(ctx):
    """Inicia um mix com times aleatórios, sem nível GC."""
    mix3_players.clear()
    view = Mix3View()
    await ctx.send(
        "🎮 **MIX 3 ABERTO! (Times Aleatórios)**\n"
        "Sem necessidade de informar nível. Times sorteados aleatoriamente!\n\n"
        "Clique em **Entrar** para participar (0/10):",
        view=view,
    )


@bot.command()
async def resetmix(ctx):
    """Reseta a fila do mix."""
    players.clear()
    await ctx.send("🔄 Mix resetado! Use `!mix` para iniciar um novo.")


@bot.command(name="Fmix")
async def fmix(ctx):
    """Cancela o mix atual e limpa a fila."""
    if not players:
        await ctx.send("❌ Não há mix ativo para cancelar.")
        return
    players.clear()
    await ctx.send("🚫 **Mix cancelado!** A fila foi limpa. Use `!mix` para iniciar um novo.")


@bot.command()
async def players_list(ctx):
    """Mostra os jogadores na fila do mix."""
    if not players:
        await ctx.send("Nenhum jogador na fila.")
        return
    msg = f"**Jogadores na fila ({len(players)}/10):**\n"
    for i, (p, lvl) in enumerate(players.items(), 1):
        msg += f"{i}. {p.display_name} *(Nível {lvl})*\n"
    await ctx.send(msg)


@bot.command()
async def rank(ctx):
    """Top 10 jogadores com mais vitórias."""
    stats = load_stats()
    if not stats:
        await ctx.send("Nenhuma partida registrada ainda.")
        return

    sorted_players = sorted(stats.items(), key=lambda x: x[1]["wins"], reverse=True)[:10]

    msg = "🏆 **TOP 10 — MAIS VITÓRIAS**\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, (uid, data) in enumerate(sorted_players, 1):
        medal = medals[i - 1] if i <= 3 else f"`{i}.`"
        msg += f"{medal} **{data['name']}** — {data['wins']}W / {data['losses']}L\n"

    await ctx.send(msg)


@bot.command()
async def derrota(ctx):
    """Top 10 jogadores com mais derrotas."""
    stats = load_stats()
    if not stats:
        await ctx.send("Nenhuma partida registrada ainda.")
        return

    sorted_players = sorted(stats.items(), key=lambda x: x[1]["losses"], reverse=True)[:10]

    msg = "💀 **TOP 10 — MAIS DERROTAS**\n\n"
    for i, (uid, data) in enumerate(sorted_players, 1):
        msg += f"`{i}.` **{data['name']}** — {data['losses']}L / {data['wins']}W\n"

    await ctx.send(msg)


@bot.command(name="mixtest")
async def mixtest(ctx):
    """Mix de teste: 2 jogadores, sem nível, mesmo jogador pode entrar 2x."""
    mix_test_players.clear()
    view = MixTestView()
    await ctx.send(
        "🧪 **MIX TESTE ABERTO!**\n"
        "Máximo de 2 jogadores. Pode entrar 2x para testar!\n\n"
        "Clique em **Entrar** para participar (0/2):",
        view=view,
    )


class CleanRankButtonView(discord.ui.View):
    """Sends a button that opens the password modal."""
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="🔑 Inserir Senha", style=discord.ButtonStyle.danger)
    async def open_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CleanRankModal())


@bot.command(name="CleanRank")
async def clean_rank(ctx):
    """Reseta o ranking com senha."""
    view = CleanRankButtonView()
    await ctx.send(
        "⚠️ **Resetar o Ranking?** Clique no botão e insira a senha para confirmar:",
        view=view,
    )


token = os.getenv("DISCORD_TOKEN")
if not token:
    raise ValueError("DISCORD_TOKEN não encontrado. Configure o secret DISCORD_TOKEN.")

bot.run(token)
