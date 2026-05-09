using System.Text.Json;
using CrossChat;

var configPath = "config.json";
string? host = null;
int? port = null;
string? serverId = null;

for (int i = 0; i < args.Length; i++)
{
    switch (args[i])
    {
        case "--config":
        case "-c":
            configPath = args[++i];
            break;
        case "--host":
            host = args[++i];
            break;
        case "--port":
            port = int.Parse(args[++i]);
            break;
        case "--server-id":
            serverId = args[++i];
            break;
        case "--help":
        case "-h":
            Console.WriteLine("Usage: CrossChat [--config <path>] [--host <host>] [--port <port>] [--server-id <id>]");
            return 0;
    }
}

var config = JsonSerializer.Deserialize<Dictionary<string, object>>(File.ReadAllText(configPath)) ?? [];
var chat = new CrossChatHost(
    config: config,
    host: host,
    port: port,
    serverId: serverId
);

string[] fakeNames = ["Alice", "Bob", "Charlie", "Diana", "Eve", "Frank", "Grace", "Hank"];
var rng = Random.Shared;
var fakeUserIds = new List<int>();

var count = rng.Next(1, 3);
Console.WriteLine($"Adding {count} immediate fake user(s)...");
for (int i = 0; i < count; i++)
{
    var name = "Imm" + fakeNames[rng.Next(fakeNames.Length)];
    var uid = await chat.State.AddUser(name);
    fakeUserIds.Add(uid);
    Console.WriteLine($"  Added user #{uid}: {name}");
}

_ = Task.Run(async () =>
{
    await Task.Delay(4000);
    Console.WriteLine("Adding late user...");
    var uid = await chat.State.AddUser("LateUser1");
    fakeUserIds.Add(uid);
    Console.WriteLine($"  Added late user #{uid}: LateUser1");
});

_ = Task.Run(async () =>
{
    await Task.Delay(6000);
    foreach (var uid in fakeUserIds)
    {
        var ownServer = chat.State.Me();
        if (ownServer.Users.TryGetValue(uid, out var user))
        {
            var payload = JsonSerializer.Serialize(new { say = $"Hello from user {uid}" });
            foreach (var kv in chat.State.Servers)
            {
                if (kv.Key != chat.State.OwnId && kv.Value.Online)
                {
                    await chat.State.Publish($"m/{chat.State.OwnId}/{kv.Key}/say/{uid}", payload);
                }
            }
            Console.WriteLine($"  Sent message from #{uid}");
        }
    }
});

await chat.RunAsync();
return 0;
