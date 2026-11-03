<?php

class Pgsql
{
    public static function query($min, $max, $limit)
    {
        $pg = pg_pconnect("host=localhost port=5432 dbname=benchmark user=bench password=bench");

        $result = pg_query_params(
                        $pg,
                        'SELECT id, name, category, price, quantity, active, tags, rating_score, rating_count FROM items WHERE price BETWEEN $1 AND $2 LIMIT $3',
                        [$min, $max, $limit]
                    );

        $data = [];
        while ($row = pg_fetch_assoc($result)) {
            $data[] = [
                'id' => $row['id'],
                'name' => $row['name'],
                'category' => $row['category'],
                'price' => $row['price'],
                'quantity' => $row['quantity'],
                'active' => (bool) $row["active"],
                'tags' => json_decode($row["tags"], true),
                'rating' => [
                    "score" => $row["rating_score"],
                    "count" => $row["rating_count"]
                ],
            ];
        }
        return json_encode(['items' => $data, 'count' => count($data)],
                            JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    }
}
