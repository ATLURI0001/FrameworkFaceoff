package com.httparena.spring.boot;

import org.springframework.web.socket.WebSocketMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.AbstractWebSocketHandler;

public class EchoWebSocketHandler extends AbstractWebSocketHandler {
    @Override
    public void handleMessage(final WebSocketSession session, final WebSocketMessage<?> message) throws Exception {
        session.sendMessage(message);
    }
}
