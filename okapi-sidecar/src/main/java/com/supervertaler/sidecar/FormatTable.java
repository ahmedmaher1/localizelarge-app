package com.supervertaler.sidecar;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

/**
 * The table of file formats: extension → Okapi filter configuration.
 * Read from {@code formats.json} on the class path. The app reads the same file.
 */
public final class FormatTable {

    /** One row of the table. */
    public static final class Format {
        public final List<String> extensions;
        public final String configId;
        public final String filterClass;
        public final String description;
        public final boolean importable;
        public final Map<String, Object> parameters;

        Format(List<String> extensions, String configId, String filterClass,
               String description, boolean importable, Map<String, Object> parameters) {
            this.extensions = Collections.unmodifiableList(extensions);
            this.configId = configId;
            this.filterClass = filterClass;
            this.description = description;
            this.importable = importable;
            this.parameters = Collections.unmodifiableMap(parameters);
        }
    }

    private final List<Format> formats;
    private final Map<String, Format> byExtension;

    private FormatTable(List<Format> formats) {
        this.formats = Collections.unmodifiableList(formats);
        Map<String, Format> map = new LinkedHashMap<>();
        for (Format f : formats) {
            for (String ext : f.extensions) {
                if (map.put(ext, f) != null) {
                    throw new IllegalStateException("formats.json lists " + ext + " twice");
                }
            }
        }
        this.byExtension = Collections.unmodifiableMap(map);
    }

    /** Load {@code formats.json} from the class path. */
    public static FormatTable load() {
        try (InputStream in = FormatTable.class.getResourceAsStream("/formats.json")) {
            if (in == null) throw new IllegalStateException("formats.json is missing");
            return parse(new ObjectMapper().readTree(in));
        } catch (IOException e) {
            throw new IllegalStateException("formats.json cannot be read", e);
        }
    }

    static FormatTable parse(JsonNode root) {
        List<Format> list = new ArrayList<>();
        for (JsonNode node : root.path("formats")) {
            List<String> exts = new ArrayList<>();
            for (JsonNode e : node.path("extensions")) {
                String ext = e.asText().toLowerCase(Locale.ROOT);
                if (!ext.startsWith(".")) {
                    throw new IllegalStateException("Extension must start with a dot: " + ext);
                }
                exts.add(ext);
            }
            String configId = node.path("configId").asText("");
            String filterClass = node.path("filterClass").asText("");
            if (exts.isEmpty() || configId.isEmpty() || filterClass.isEmpty()) {
                throw new IllegalStateException("Incomplete row in formats.json: " + node);
            }
            Map<String, Object> params = new LinkedHashMap<>();
            Iterator<Map.Entry<String, JsonNode>> it = node.path("parameters").fields();
            while (it.hasNext()) {
                Map.Entry<String, JsonNode> p = it.next();
                JsonNode v = p.getValue();
                if (v.isBoolean()) params.put(p.getKey(), v.booleanValue());
                else if (v.isInt()) params.put(p.getKey(), v.intValue());
                else params.put(p.getKey(), v.asText());
            }
            list.add(new Format(exts, configId, filterClass,
                    node.path("description").asText(configId),
                    node.path("import").asBoolean(true), params));
        }
        if (list.isEmpty()) throw new IllegalStateException("formats.json has no formats");
        return new FormatTable(list);
    }

    public List<Format> all() {
        return formats;
    }

    /** The filter classes to register, each once, in table order. */
    public Set<String> filterClasses() {
        Set<String> classes = new LinkedHashSet<>();
        for (Format f : formats) classes.add(f.filterClass);
        return classes;
    }

    public Set<String> extensions() {
        return byExtension.keySet();
    }

    /** The row for a file name, or null when its extension is not in the table. */
    public Format forFile(String filename) {
        String lower = filename.toLowerCase(Locale.ROOT);
        int dot = lower.lastIndexOf('.');
        if (dot < 0) return null;
        return byExtension.get(lower.substring(dot));
    }
}
