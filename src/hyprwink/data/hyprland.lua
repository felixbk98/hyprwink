-- Hyprwink for a Hyprland Lua config: copy these blocks into your own files
-- (shortcuts into your bindings, the rule into your window rules). Keep the
-- "-- Hyprwink" and "-- End Hyprwink" lines: `hyprwink remove` removes
-- everything between them.

-- Hyprwink: shortcuts
local hyprwink = "hyprwink"
hl.bind("SUPER + G", hl.dsp.exec_cmd(hyprwink .. " toggle"), { description = "Hyprwink on/off" })
hl.bind("SUPER + ALT + G", hl.dsp.exec_cmd(hyprwink .. " ui --settings"), { description = "Hyprwink: settings" })
-- Dictation: Ctrl + Space starts and stops; while it runs Hyprwink binds
-- Escape (cancel) and Enter (stop and send) itself.
hl.bind("CTRL + SPACE", hl.dsp.exec_cmd(hyprwink .. " dictate toggle"), { description = "Dictation on/off" })
-- End Hyprwink

-- Hyprwink: mini view in the bottom right corner, always on top, never takes the focus
hl.window_rule({
  match = { title = "^Hyprwink Mini$" },
  float = true,
  pin = true,
  no_focus = true,
  no_shadow = true,
  size = { 384, 216 },
  move = { "monitor_w - window_w - 24", "monitor_h - window_h - 24" },
})
-- End Hyprwink
