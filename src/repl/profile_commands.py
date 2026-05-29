"""Profile management commands — /profile."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.formatting import bold, dim, green, cyan, red

if TYPE_CHECKING:
    from src.repl.repl import Repl


def handle_profile(repl: "Repl", cmd: str) -> None:
    """Handle /profile command — save, load, list, delete configuration profiles."""
    from src.profiles import save_profile, load_profile, list_profiles, delete_profile

    parts = cmd.strip().split(maxsplit=2)
    subcommand = parts[1].lower() if len(parts) > 1 else "list"

    if subcommand == "save":
        if len(parts) < 3:
            print(f"  {dim('Usage: /profile save <name>')}")
            return
        name = parts[2].strip()
        profile_data = {
            "model": repl.llm.model,
            "max_tokens": repl.max_tokens,
            "temperature": repl.llm.temperature,
            "top_p": repl.llm.top_p,
            "system_prompt": repl.system_prompt,
            "custom_persona": repl._custom_persona,
        }
        try:
            filepath = save_profile(name, profile_data, repl.working_directory)
            print(f"  {green('✓')} {dim('Profile saved to')} {cyan(filepath)}")
        except Exception as exc:
            print(f"  {red('✗ Error saving profile:')} {exc}")

    elif subcommand == "load":
        if len(parts) < 3:
            print(f"  {dim('Usage: /profile load <name>')}")
            return
        name = parts[2].strip()
        profile = load_profile(name, repl.working_directory)
        if profile is None:
            print(f"  {dim('Profile not found:')} {cyan(name)}")
            print(f"  {dim('Use /profile list to see available profiles.')}")
            return
        # Apply profile values (only non-default fields)
        applied: list[str] = []
        if profile.model:
            repl.llm.model = profile.model
            applied.append(f"model={profile.model}")
        if profile.max_tokens > 0:
            repl.max_tokens = profile.max_tokens
            applied.append(f"max_tokens={profile.max_tokens}")
        if profile.temperature > 0:
            repl.llm.temperature = profile.temperature
            applied.append(f"temperature={profile.temperature}")
        if profile.top_p > 0:
            repl.llm.top_p = profile.top_p
            applied.append(f"top_p={profile.top_p}")
        if profile.system_prompt:
            repl.system_prompt = profile.system_prompt
            applied.append("system_prompt=✓")
        if profile.custom_persona:
            repl._custom_persona = profile.custom_persona
            applied.append("persona=✓")
        print(f"  {green('✓')} {bold(f'Profile loaded: {profile.name}')}")
        for item in applied:
            print(f"    {dim('•')} {cyan(item)}")

    elif subcommand == "list":
        profiles = list_profiles(repl.working_directory)
        if not profiles:
            print(f"  {dim('No saved profiles found.')}")
            print(f"  {dim('Use /profile save <name> to save the current configuration.')}")
            return
        print(f"  {bold('Saved Profiles')}")
        print()
        for p in profiles:
            model_str = p.model if p.model else "(default)"
            print(f"  {cyan(p.name.ljust(20))} {dim(model_str)}")

    elif subcommand == "delete":
        if len(parts) < 3:
            print(f"  {dim('Usage: /profile delete <name>')}")
            return
        name = parts[2].strip()
        if delete_profile(name, repl.working_directory):
            print(f"  {green('✓')} {dim('Profile deleted:')} {cyan(name)}")
        else:
            print(f"  {dim('Profile not found:')} {cyan(name)}")

    else:
        print(f"  {dim('Unknown profile command. Usage:')}")
        print(f"  {dim('  /profile list              — list all profiles')}")
        print(f"  {dim('  /profile load <name>       — load a configuration profile')}")
        print(f"  {dim('  /profile save <name>       — save current config as profile')}")
        print(f"  {dim('  /profile delete <name>     — delete a profile')}")
