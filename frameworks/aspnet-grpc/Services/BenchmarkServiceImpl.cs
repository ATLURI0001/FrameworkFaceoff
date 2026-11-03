using Benchmark;
using Grpc.Core;

namespace AspnetGrpc.Services;

public class BenchmarkServiceImpl : BenchmarkService.BenchmarkServiceBase
{
    public override Task<SumReply> GetSum(SumRequest request, ServerCallContext context)
    {
        return Task.FromResult(new SumReply { Result = request.A + request.B });
    }

    // Server streaming — emit `count` replies for one request.
    public override async Task StreamSum(
        StreamRequest request,
        IServerStreamWriter<SumReply> responseStream,
        ServerCallContext context)
    {
        var sum = request.A + request.B;
        var count = request.Count <= 0 ? 1 : request.Count;
        for (var i = 0; i < count; i++)
        {
            await responseStream.WriteAsync(new SumReply { Result = sum + i });
        }
    }

    // Client streaming — aggregate every incoming request into one final total.
    public override async Task<SumReply> CollectSum(
        IAsyncStreamReader<SumRequest> requestStream,
        ServerCallContext context)
    {
        var total = 0;
        await foreach (var req in requestStream.ReadAllAsync())
        {
            total += req.A + req.B;
        }
        return new SumReply { Result = total };
    }

    // Bidirectional streaming — one reply per incoming request on a persistent stream.
    public override async Task EchoSum(
        IAsyncStreamReader<SumRequest> requestStream,
        IServerStreamWriter<SumReply> responseStream,
        ServerCallContext context)
    {
        await foreach (var req in requestStream.ReadAllAsync())
        {
            await responseStream.WriteAsync(new SumReply { Result = req.A + req.B });
        }
    }
}
