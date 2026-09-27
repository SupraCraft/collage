module github.com/SupraCraft/collage/tools/truenas-readonly-probe

go 1.25.0

require github.com/deevus/truenas-go v0.5.0

// Match the already-qualified dependency selections used by
// SemperSupra/garm-provider-truenas while keeping this probe isolated.
require (
	al.essio.dev/pkg/shellescape v1.6.0 // indirect
	github.com/dustin/go-humanize v1.0.1 // indirect
	github.com/gorilla/websocket v1.5.4-0.20240702125206-a62d9d2a8413 // indirect
	golang.org/x/crypto v0.53.0 // indirect
	golang.org/x/net v0.56.0 // indirect
	golang.org/x/sys v0.46.0 // indirect
	golang.org/x/time v0.14.0 // indirect
)
