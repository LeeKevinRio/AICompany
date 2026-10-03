using System;

// DTOs mirror work/manjong-unity/api-contract.md v0.3 exactly (everything goes over the WebSocket).
// JsonUtility rules: [Serializable] classes, public fields, camelCase names identical to the contract.
namespace Manjong.Net
{
    // ---------- Account ----------

    [Serializable]
    public class PlayerDto
    {
        public string id;
        public string nickname;
        public int coins;
        public int handsPlayed;
        public int handsWon;
        public int selfDraws;
        public int dealIns;
        public int bestTai;
    }

    // ---------- Leaderboard ----------

    [Serializable]
    public class LeaderboardEntry
    {
        public int rank;
        public string nickname;
        public int coins;
        public int handsWon;
        public int bestTai;
        public bool isMe;
    }

    // ---------- WebSocket envelopes ----------

    /// <summary>Client -> server. type: auth | guest | me | nickname | relief | leaderboard | start | action | ping.</summary>
    [Serializable]
    public class ClientMessage
    {
        public string type;
        /// <summary>Echoed back as ServerMessage.replyTo on the reply / error.</summary>
        public string requestId;
        public string token;
        public string actionId;
        public string nickname;
    }

    /// <summary>Server -> client. type: auth_ok | player | leaderboard | step | state | error | pong.</summary>
    [Serializable]
    public class ServerMessage
    {
        public string type;
        public int seq;
        /// <summary>requestId of the request this answers; "" for pushes (step / state / post-hand player).</summary>
        public string replyTo;
        /// <summary>Only on auth_ok after "guest": the new account's token (store it).</summary>
        public string token;
        public PlayerDto player;
        public LeaderboardEntry[] entries;
        public StepDto step;
        public GameView view;
        // INVALID_TOKEN | AUTH_TIMEOUT | UNAUTHORIZED | INVALID_NICKNAME | RELIEF_NOT_ELIGIBLE | NOT_ENOUGH_COINS
        // | NO_GAME | ILLEGAL_ACTION | BAD_MESSAGE | INTERNAL
        public string code;
        public string message;
    }

    // ---------- Game ----------

    [Serializable]
    public class EventDto
    {
        // hand_start | draw | flower | discard | chi | pon | kan | ankan | kakan | win | exhaustive | game_end
        public string type;
        public int seat;
        public string tile;
        public string[] tiles;
        public string text;
    }

    [Serializable]
    public class StepDto
    {
        // "event" is a C# keyword; the verbatim identifier keeps the serialized field name "event".
        public EventDto @event;
        public GameView view;
    }

    [Serializable]
    public class WaitDto
    {
        public string tile;
        /// <summary>Copies still unseen from my point of view.</summary>
        public int left;
    }

    [Serializable]
    public class MeldDto
    {
        // chi | pon | kan | ankan | kakan
        public string type;
        public string[] tiles;
        public int fromSeat;
    }

    [Serializable]
    public class PlayerView
    {
        public int seat;
        public string name;
        // me | bear | cat | rabbit
        public string avatar;
        public bool isAi;
        public string seatWind;
        public int handCount;
        public string[] hand;
        public string drawnTile;
        public MeldDto[] melds;
        public string[] flowers;
        public string[] discards;
        public int sessionDelta;
    }

    [Serializable]
    public class OptionDto
    {
        public string id;
        // discard | tsumo | ron | pon | kan | chi | ankan | kakan | pass | next
        public string type;
        public string tile;
        public string[] tiles;
        public string label;
        /// <summary>discard only: what I would be waiting on after discarding this tile (empty = not ready).</summary>
        public WaitDto[] waits;
        /// <summary>tsumo / ron only: tai of this win (without dealer tai); otherwise -1.</summary>
        public int tai;
    }

    [Serializable]
    public class TaiItem
    {
        public string name;
        public int tai;
    }

    [Serializable]
    public class HandResult
    {
        // win | exhaustive
        public string kind;
        public int winnerSeat;
        public int loserSeat;
        public bool selfDraw;
        public string winningTile;
        public int totalTai;
        public TaiItem[] items;
        public int dealerTai;
        public int[] deltas;
        public bool gameOver;
    }

    [Serializable]
    public class GameView
    {
        public string gameId;
        // playing | hand_end | game_end
        public string phase;
        public int handNo;
        public string roundWind;
        public int dealerSeat;
        public int dealerStreak;
        public int mySeat;
        public int turnSeat;
        public int wallRemaining;
        public int lastDiscardSeat;
        public string lastDiscardTile;
        /// <summary>Persistent coins including this hand's settlement; never below 0.</summary>
        public int myCoins;
        /// <summary>phase = game_end: "rounds_complete" or "bankrupt"; otherwise "".</summary>
        public string endReason;
        /// <summary>Tiles I am currently waiting on (empty while I have to discard; see discard options' waits).</summary>
        public WaitDto[] myWaits;
        public PlayerView[] players;
        public OptionDto[] options;
        public bool hasResult;
        public HandResult result;
    }

    /// <summary>Null-safe accessors so UI code never trips over a missing array or string.</summary>
    public static class DtoUtil
    {
        static readonly string[] EmptyStrings = new string[0];

        public static string[] Safe(string[] a)
        {
            return a ?? EmptyStrings;
        }

        public static string Safe(string s)
        {
            return s ?? "";
        }

        public static T[] Safe<T>(T[] a)
        {
            return a ?? new T[0];
        }

        public static PlayerView Player(GameView v, int seat)
        {
            if (v == null || v.players == null) return null;
            for (int i = 0; i < v.players.Length; i++)
            {
                if (v.players[i] != null && v.players[i].seat == seat) return v.players[i];
            }
            if (seat >= 0 && seat < v.players.Length) return v.players[seat];
            return null;
        }

        public static OptionDto FindOption(GameView v, string id)
        {
            if (v == null || v.options == null) return null;
            for (int i = 0; i < v.options.Length; i++)
            {
                if (v.options[i] != null && v.options[i].id == id) return v.options[i];
            }
            return null;
        }

        public static bool HasDiscardOption(GameView v)
        {
            if (v == null || v.options == null) return false;
            for (int i = 0; i < v.options.Length; i++)
            {
                if (v.options[i] != null && v.options[i].type == "discard") return true;
            }
            return false;
        }

        public static bool HasOptions(GameView v)
        {
            return v != null && v.options != null && v.options.Length > 0;
        }
    }
}
