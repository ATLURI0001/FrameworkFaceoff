package com.httparena;

import jakarta.inject.Singleton;
import org.jboss.resteasy.reactive.server.ServerResponseFilter;
import io.vertx.core.MultiMap;
import io.vertx.core.http.HttpHeaders;
import io.vertx.core.http.HttpServerResponse;

@Singleton
public class ServerHeaderFilter {

    private static final CharSequence SERVER_HEADER_NAME = HttpHeaders.createOptimized("Server");
    private static final CharSequence SERVER_HEADER_VALUE = HttpHeaders.createOptimized("quarkus-jvm");

    @ServerResponseFilter
    public void filter(HttpServerResponse response) {
        response.headers().add(SERVER_HEADER_NAME, SERVER_HEADER_VALUE);
    }
}
