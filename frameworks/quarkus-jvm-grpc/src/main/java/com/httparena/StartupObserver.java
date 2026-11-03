package com.httparena;

import io.quarkus.runtime.StartupEvent;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.enterprise.event.Observes;

@ApplicationScoped
public class StartupObserver {

    void onStart(@Observes StartupEvent ev) {
        System.out.println("Application started.");
    }
}
