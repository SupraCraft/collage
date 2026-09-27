package main

import (
	"reflect"
	"testing"
)

func TestCollectCollageMetadataOnlyAllowlistedKeys(t *testing.T) {
	config := map[string]any{
		"minecraft": map[string]any{
			"additional_envs": []any{
				map[string]any{"name": "SUPRACRAFT_COLLAGE_MANAGED", "value": "true"},
				map[string]any{"name": "SUPRACRAFT_COLLAGE_SCHEMA", "value": "1"},
				map[string]any{"name": "SUPRACRAFT_COLLAGE_MANAGER_ID", "value": "manager-rdte"},
				map[string]any{"name": "SUPRACRAFT_COLLAGE_FLEET_ID", "value": "rdte"},
				map[string]any{"name": "SUPRACRAFT_COLLAGE_SERVICE_ID", "value": "11111111-1111-4111-8111-111111111111"},
				map[string]any{"name": "SUPRACRAFT_COLLAGE_TASK_NAME", "value": "CollageReAdopt"},
				map[string]any{"name": "SUPRACRAFT_COLLAGE_TASK_SERVICE_ID", "value": "37"},
				map[string]any{"name": "SUPRACRAFT_COLLAGE_WORLD_ID", "value": "world-rdte-001"},
				map[string]any{"name": "SOME_SECRET", "value": "must-not-escape"},
			},
		},
		"unrelated_secret": "must-not-escape",
	}

	got := map[string]string{}
	collectCollageMetadata(config, got)
	want := map[string]string{
		"SUPRACRAFT_COLLAGE_MANAGED":         "true",
		"SUPRACRAFT_COLLAGE_SCHEMA":          "1",
		"SUPRACRAFT_COLLAGE_MANAGER_ID":      "manager-rdte",
		"SUPRACRAFT_COLLAGE_FLEET_ID":        "rdte",
		"SUPRACRAFT_COLLAGE_SERVICE_ID":      "11111111-1111-4111-8111-111111111111",
		"SUPRACRAFT_COLLAGE_TASK_NAME":       "CollageReAdopt",
		"SUPRACRAFT_COLLAGE_TASK_SERVICE_ID": "37",
		"SUPRACRAFT_COLLAGE_WORLD_ID":        "world-rdte-001",
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("metadata mismatch\n got: %#v\nwant: %#v", got, want)
	}
}

func TestMissingMetadata(t *testing.T) {
	meta := map[string]string{
		"SUPRACRAFT_COLLAGE_MANAGED": "true",
		"SUPRACRAFT_COLLAGE_SCHEMA":  "1",
	}
	got := missingMetadata(meta)
	if len(got) != 6 {
		t.Fatalf("expected six missing fields, got %v", got)
	}
}

func TestDirectKeyShapeIsSupportedWithoutLeakingOtherKeys(t *testing.T) {
	config := map[string]any{
		"SUPRACRAFT_COLLAGE_MANAGED": "true",
		"SUPRACRAFT_COLLAGE_SCHEMA":  "1",
		"password":                   "must-not-escape",
	}
	got := map[string]string{}
	collectCollageMetadata(config, got)
	want := map[string]string{
		"SUPRACRAFT_COLLAGE_MANAGED": "true",
		"SUPRACRAFT_COLLAGE_SCHEMA":  "1",
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("metadata mismatch: got %#v want %#v", got, want)
	}
}
