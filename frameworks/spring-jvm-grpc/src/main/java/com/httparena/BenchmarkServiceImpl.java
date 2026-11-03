package com.httparena;

import benchmark.BenchmarkServiceGrpc;
import benchmark.Benchmark.SumRequest;
import benchmark.Benchmark.SumReply;
import io.grpc.stub.StreamObserver;
import net.devh.boot.grpc.server.service.GrpcService;

@GrpcService
public class BenchmarkServiceImpl extends BenchmarkServiceGrpc.BenchmarkServiceImplBase {

    @Override
    public void getSum(SumRequest request, StreamObserver<SumReply> responseObserver) {
        SumReply reply = SumReply.newBuilder()
                .setResult(request.getA() + request.getB())
                .build();
        responseObserver.onNext(reply);
        responseObserver.onCompleted();
    }
}
