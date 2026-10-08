def open_dataset(config):
    registry = config.registry()
    plugin = registry.get("dataset", config.dataset)
    return plugin.hooks["open"](
        config, registry.parameters("dataset", config.dataset, config.dataset_params)
    )
