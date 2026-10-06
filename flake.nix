{
  description = "emcommOS development shell (pinned tooling)";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAll = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in
    {
      devShells = forAll (pkgs: {
        default = pkgs.mkShell {
          packages = with pkgs; [ python312 uv nfpm shellcheck actionlint gnupg rclone git jq ];
          shellHook = ''
            export UV_PYTHON=${pkgs.python312}/bin/python3
            command -v podman >/dev/null || echo "note: install podman from your distro for package builds"
          '';
        };
      });
    };
}
