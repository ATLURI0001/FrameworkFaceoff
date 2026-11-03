package com.httparena.spring.boot;

import java.util.List;

public record TotalItems(List<TotalItem> items, long count) {}
