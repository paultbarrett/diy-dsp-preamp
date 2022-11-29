table.insert (bluez_monitor.rules, {

    matches = {
      {
        -- Matches all sources.
        { "node.name", "matches", "bluez_input.*" },
      },
    },
    apply_properties = {
      -- keep name in sync with pipewire.conf
      ["node.target"] = "alsa-sink-loopback2",
    },

})
