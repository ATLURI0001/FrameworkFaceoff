package main

import (
	"fmt"
	"net"
	"net/http"
	"runtime"

	"github.com/gobwas/ws"
	"github.com/gobwas/ws/wsutil"
)

func main() {
	runtime.GOMAXPROCS(runtime.NumCPU())

	http.HandleFunc("/ws", func(w http.ResponseWriter, r *http.Request) {
		conn, _, _, err := ws.UpgradeHTTP(r, w)
		if err != nil {
			return
		}
		defer conn.Close()

		for {
			msg, op, err := wsutil.ReadClientData(conn)
			if err != nil {
				return
			}
			if err := wsutil.WriteServerMessage(conn, op, msg); err != nil {
				return
			}
		}
	})

	ln, err := net.Listen("tcp", ":8080")
	if err != nil {
		panic(err)
	}
	fmt.Println("Application started.")
	if err := http.Serve(ln, nil); err != nil {
		panic(err)
	}
}
