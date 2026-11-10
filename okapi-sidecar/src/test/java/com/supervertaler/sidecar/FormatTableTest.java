package com.supervertaler.sidecar;

import net.sf.okapi.common.filters.FilterConfiguration;
import net.sf.okapi.common.filters.FilterConfigurationMapper;
import net.sf.okapi.common.filters.IFilter;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** Checks every row of formats.json against the Okapi version on the class path. */
class FormatTableTest {

    private static final List<String> REQUIRED = List.of(
            ".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp", ".html", ".htm",
            ".xlf", ".xliff", ".xlf2", ".po", ".idml", ".md", ".json", ".yaml", ".yml",
            ".properties", ".csv", ".txt", ".xml", ".vtt", ".srt", ".tmx");

    @Test
    void everyConfigurationIdExistsInThisOkapiVersion() {
        FormatTable table = FormatTable.load();
        FilterConfigurationMapper mapper = new FilterConfigurationMapper();
        for (String filterClass : table.filterClasses()) {
            mapper.addConfigurations(filterClass);
        }
        for (FormatTable.Format f : table.all()) {
            FilterConfiguration config = mapper.getConfiguration(f.configId);
            assertNotNull(config, "Okapi has no configuration " + f.configId);
            assertEquals(f.filterClass, config.filterClass, f.configId);
            IFilter filter = mapper.createFilter(f.configId);
            assertNotNull(filter, "Okapi cannot create a filter for " + f.configId);
        }
    }

    @Test
    void theTableCoversTheV1Formats() {
        FormatTable table = FormatTable.load();
        for (String ext : REQUIRED) {
            assertTrue(table.extensions().contains(ext), ext);
        }
    }

    @Test
    void lookupIsByExtensionAndIgnoresCase() {
        FormatTable table = FormatTable.load();
        assertEquals("okf_openxml", table.forFile("Report.DOCX").configId);
        assertEquals("okf_openoffice", table.forFile("a.b.odt").configId);
        assertEquals("okf_regex-srt", table.forFile("film.srt").configId);
        assertNull(table.forFile("picture.png"));
        assertNull(table.forFile("no-extension"));
        assertFalse(table.forFile("memory.tmx").importable);
    }

    @Test
    void theServiceListsEveryExtension() {
        FilterService service = new FilterService();
        assertEquals(FormatTable.load().extensions().size(), service.getSupportedFilters().size());
    }
}
