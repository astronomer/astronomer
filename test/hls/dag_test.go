package e2e_test

import (
	"flag"
	"io/ioutil"
	"os"
	"strings"
	"testing"

	"github.com/hofstadter-io/hof/lib/yagu"
	"github.com/hofstadter-io/hof/script"
)

var (
	ENV = flag.String("env", ".env", "environment file to expose to scripts")
	DIR = flag.String("dir", "tests/e2e", "base directory to search for scripts")
	GLOB = flag.String("glob", "*.hls", "glob for matching script names from the base dir")
	WORK = flag.String("work", ".hls/e2e", "working directory for the scripts")
	LEAVE = flag.Bool("leave", false, "leave the script workdir in place for inspection")
)

func envSetup(env *script.Env) error {
	// ENV vars in your shell you want added to the tests env
	var keys = []string{
		"USER",
		"GITHUB_TOKEN",
		"ASTRO_EMAIL",
	}

	for _, key := range keys {
		val := os.Getenv(key)
		if val != "" {
			env.Vars = append(env.Vars, key+"="+val)
		}
	}

	// .env can contain lines of ENV=VAR
	content, err := ioutil.ReadFile(*ENV)
	if err != nil {
		// ignore errors, as the file likely doesn't exist
		return nil
	}

	for _, line := range strings.Split(string(content), "\n") {
		if strings.Contains(line, "=") {
			if line[0:1] == "#" {
				continue
			}
			env.Vars = append(env.Vars, line)
		}
	}


	return nil
}

func TestAstroPlatform(t *testing.T) {
	yagu.Mkdir(".hls/e2e")
	script.Run(t, script.Params{
		Setup: envSetup,
		Dir: *DIR,
		Glob: *GLOB,
		WorkdirRoot: *WORK,
		TestWork: *LEAVE,
	})
}

/*
func TestDagBugs(t *testing.T) {
	yagu.Mkdir(".hls/bugs")
	script.Run(t, script.Params{
		Setup: envSetup,
		Dir: "tests/bugs",
		WorkdirRoot: ".hls/bugs",
	})
}
*/

