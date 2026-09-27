package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"

	truenas "github.com/deevus/truenas-go"
	tnclient "github.com/deevus/truenas-go/client"
)

var collageKeys = map[string]struct{}{
	"SUPRACRAFT_COLLAGE_MANAGED":    {},
	"SUPRACRAFT_COLLAGE_SCHEMA":     {},
	"SUPRACRAFT_COLLAGE_MANAGER_ID": {},
	"SUPRACRAFT_COLLAGE_FLEET_ID":   {},
	"SUPRACRAFT_COLLAGE_SERVICE_ID": {},
	"SUPRACRAFT_COLLAGE_WORLD_ID":   {},
}

type output struct {
	SchemaVersion    int               `json:"schema_version"`
	Result           string            `json:"result"`
	TrueNASVersion   string            `json:"truenas_version"`
	AppName          string            `json:"app_name"`
	AppState         string            `json:"app_state"`
	CustomApp        bool              `json:"custom_app"`
	AppVersion       string            `json:"app_version"`
	ConfigPresent    bool              `json:"config_present"`
	ContainerCount   int               `json:"container_count"`
	CollageMetadata  map[string]string `json:"collage_metadata"`
	MissingMetadata  []string          `json:"missing_collage_metadata,omitempty"`
	MetadataRequired bool              `json:"metadata_required"`
}

func envOr(value, key string) string {
	if strings.TrimSpace(value) != "" {
		return strings.TrimSpace(value)
	}
	return strings.TrimSpace(os.Getenv(key))
}

func collectCollageMetadata(value any, out map[string]string) {
	switch v := value.(type) {
	case map[string]any:
		if rawName, ok := v["name"]; ok {
			name, ok := rawName.(string)
			if ok {
				if _, wanted := collageKeys[name]; wanted {
					switch rawValue := v["value"].(type) {
					case string:
						out[name] = rawValue
					case bool, float64, json.Number:
						out[name] = fmt.Sprint(rawValue)
					case nil:
						out[name] = ""
					}
				}
			}
		}
		for k, child := range v {
			if _, wanted := collageKeys[k]; wanted {
				switch typed := child.(type) {
				case string:
					out[k] = typed
				case bool, float64, json.Number:
					out[k] = fmt.Sprint(typed)
				}
			}
			collectCollageMetadata(child, out)
		}
	case []any:
		for _, child := range v {
			collectCollageMetadata(child, out)
		}
	}
}

func missingMetadata(meta map[string]string) []string {
	keys := []string{
		"SUPRACRAFT_COLLAGE_MANAGED",
		"SUPRACRAFT_COLLAGE_SCHEMA",
		"SUPRACRAFT_COLLAGE_MANAGER_ID",
		"SUPRACRAFT_COLLAGE_FLEET_ID",
		"SUPRACRAFT_COLLAGE_SERVICE_ID",
		"SUPRACRAFT_COLLAGE_WORLD_ID",
	}
	var missing []string
	for _, key := range keys {
		if strings.TrimSpace(meta[key]) == "" {
			missing = append(missing, key)
		}
	}
	return missing
}

func run() error {
	hostFlag := flag.String("host", "", "TrueNAS DNS name or IP; may also use TRUENAS_HOST")
	userFlag := flag.String("username", "", "TrueNAS username; may also use TRUENAS_USERNAME")
	appFlag := flag.String("app", "", "TrueNAS App name; may also use TRUENAS_APP_NAME")
	portFlag := flag.Int("port", 0, "TrueNAS HTTPS port; default 443 or TRUENAS_PORT")
	timeoutFlag := flag.Duration("timeout", 30*time.Second, "overall read-only probe timeout")
	requireMetadata := flag.Bool("require-collage-metadata", false, "fail unless all bounded COLLAGE ownership fields are present")
	flag.Parse()

	host := envOr(*hostFlag, "TRUENAS_HOST")
	username := envOr(*userFlag, "TRUENAS_USERNAME")
	appName := envOr(*appFlag, "TRUENAS_APP_NAME")
	apiKey := os.Getenv("TRUENAS_API_KEY")

	port := *portFlag
	if port == 0 {
		if raw := strings.TrimSpace(os.Getenv("TRUENAS_PORT")); raw != "" {
			parsed, err := strconv.Atoi(raw)
			if err != nil || parsed < 1 || parsed > 65535 {
				return errors.New("TRUENAS_PORT must be an integer from 1 to 65535")
			}
			port = parsed
		}
	}
	if port == 0 {
		port = 443
	}

	if host == "" || username == "" || appName == "" {
		return errors.New("host, username, and app name are required")
	}
	if strings.TrimSpace(apiKey) == "" {
		return errors.New("TRUENAS_API_KEY must be supplied through the environment; command-line API keys are intentionally unsupported")
	}
	if strings.Contains(host, "://") || strings.ContainsAny(host, "/@") {
		return errors.New("host must be a DNS name or IP only; URL/userinfo forms are rejected")
	}

	ctx, cancel := context.WithTimeout(context.Background(), *timeoutFlag)
	defer cancel()

	ws, err := tnclient.NewWebSocketClient(tnclient.WebSocketConfig{
		Host:               host,
		Username:           username,
		APIKey:             apiKey,
		Port:               port,
		InsecureSkipVerify: false,
		MaxRetries:         0,
		ConnectTimeout:     10 * time.Second,
	})
	if err != nil {
		return fmt.Errorf("configure TrueNAS websocket client: %w", err)
	}
	defer ws.Close()

	if err := ws.Connect(ctx); err != nil {
		return fmt.Errorf("connect/authenticate TrueNAS websocket: %w", err)
	}

	apps := truenas.NewAppService(ws, ws.Version())
	app, err := apps.GetAppWithConfig(ctx, appName)
	if err != nil {
		return fmt.Errorf("read app %q with config: %w", appName, err)
	}
	if app == nil {
		return fmt.Errorf("app %q was not found", appName)
	}

	meta := map[string]string{}
	collectCollageMetadata(app.Config, meta)
	missing := missingMetadata(meta)
	result := "PASS"
	if *requireMetadata && len(missing) != 0 {
		result = "FAIL"
	}

	report := output{
		SchemaVersion:    1,
		Result:           result,
		TrueNASVersion:   ws.Version().Raw,
		AppName:          app.Name,
		AppState:         app.State,
		CustomApp:        app.CustomApp,
		AppVersion:       app.Version,
		ConfigPresent:    app.Config != nil,
		ContainerCount:   app.ActiveWorkloads.Containers,
		CollageMetadata:  meta,
		MissingMetadata:  missing,
		MetadataRequired: *requireMetadata,
	}
	encoded, err := json.MarshalIndent(report, "", "  ")
	if err != nil {
		return fmt.Errorf("encode sanitized result: %w", err)
	}
	fmt.Println(string(encoded))

	if result != "PASS" {
		return errors.New("required COLLAGE ownership metadata was incomplete")
	}
	return nil
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, "ERROR:", err)
		os.Exit(2)
	}
}
