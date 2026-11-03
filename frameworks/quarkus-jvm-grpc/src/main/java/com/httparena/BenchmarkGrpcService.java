package com.httparena;

import benchmark.BenchmarkServiceGrpc;
import benchmark.Benchmark.SumReply;
import benchmark.Benchmark.SumRequest;
import io.grpc.stub.StreamObserver;
import io.quarkus.grpc.GrpcService;

@GrpcService
public class BenchmarkGrpcService extends BenchmarkServiceGrpc.BenchmarkServiceImplBase {

    @Override
    public void getSum(SumRequest request, StreamObserver<SumReply> responseObserver) {
        SumReply reply = SumReply.newBuilder()
                .setResult(request.getA() + request.getB())
                .build();
        responseObserver.onNext(reply);
        responseObserver.onCompleted();
    }
}
