package org.thehill.hill175.world;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.thehill.hill175.model.BuildRegion;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

final class BuildingTemplateTest {
    @Test
    void locatesRegionsCorrectlyAcrossNegativeCoordinates() {
        BuildRegion region = new BuildRegion("entry", -20, -64, -40, 30, 319, 60);
        assertEquals(List.of("r.-1.-1.mca", "r.-1.0.mca", "r.0.-1.mca", "r.0.0.mca"),
                BuildingTemplate.regionFiles(region));
    }

    @Test
    void clonesSourceTerrainWithoutIdentityEntitiesOrUnrelatedRegions(@TempDir Path runtime) throws IOException {
        Path source = prepareSource(runtime);
        BuildRegion region = new BuildRegion("entry", 0, -64, 0, 31, 319, 31);
        Path target = runtime.resolve("private-place");
        Files.createDirectories(source.resolve("playerdata"));
        Files.writeString(source.resolve("playerdata/student.dat"), "private");
        Files.createDirectories(source.resolve("entities"));
        Files.writeString(source.resolve("entities/r.0.0.mca"), "not copied");
        Files.writeString(source.resolve("level.dat"), "source identity");
        Files.writeString(source.resolve("region/r.1.0.mca"), "unrelated region");
        BuildingTemplate.copy(source, target, region);
        assertArrayEquals(Files.readAllBytes(source.resolve("region/r.0.0.mca")),
                Files.readAllBytes(target.resolve("region/r.0.0.mca")));
        assertTrue(Files.isRegularFile(target.resolve(CampusTemplateMetadata.FILE_NAME)));
        assertFalse(Files.exists(target.resolve("playerdata")));
        assertFalse(Files.exists(target.resolve("entities")));
        assertFalse(Files.exists(target.resolve("level.dat")));
        assertFalse(Files.exists(target.resolve("region/r.1.0.mca")));
        assertThrows(IOException.class, () -> BuildingTemplate.copy(source, target, region));
    }

    @Test
    void rejectsMissingSourceChunksBeforeCreatingAWorld(@TempDir Path runtime) throws IOException {
        Path source = prepareSource(runtime);
        BuildRegion region = new BuildRegion("entry", 0, -64, 0, 47, 319, 31);
        Path target = runtime.resolve("private-place");
        IllegalStateException failure = assertThrows(IllegalStateException.class, () ->
                BuildingTemplate.copy(source, target, region));
        assertTrue(failure.getMessage().contains("missing building chunk"));
        assertFalse(Files.exists(target));
    }

    @Test
    void rejectsSelectionOutsideCampusBeforeCopying(@TempDir Path runtime) throws IOException {
        Path source = prepareSource(runtime);
        Path target = runtime.resolve("private-place");
        assertThrows(IllegalStateException.class, () -> BuildingTemplate.copy(source, target,
                new BuildRegion("entry", -200, -64, 0, 31, 319, 31)));
        assertFalse(Files.exists(target));
    }

    @Test
    void extendsExteriorTerrainWithoutOverwritingStudentRegionsOrChunks(@TempDir Path runtime) throws IOException {
        Path source = prepareWideSource(runtime);
        BuildRegion original = new BuildRegion("entry", 480, -64, 0, 495, 319, 15);
        Path target = runtime.resolve("private-place");
        BuildingTemplate.copy(source, target, original);
        Path editedRegion = target.resolve("region/r.0.0.mca");
        Files.writeString(editedRegion, "student building changes");
        Files.writeString(target.resolve("region/c.30.0.mcc"), "student external chunk");
        Files.writeString(source.resolve("region/c.30.0.mcc"), "original external chunk");
        Files.writeString(source.resolve("region/c.33.0.mcc"), "new exterior chunk");
        BuildRegion viewing = new BuildRegion("entry", 480, -64, 0, 527, 319, 15);

        BuildingTemplate.copyMissingTerrain(source, target, viewing);

        assertEquals("student building changes", Files.readString(editedRegion));
        assertEquals("student external chunk", Files.readString(target.resolve("region/c.30.0.mcc")));
        assertArrayEquals(Files.readAllBytes(source.resolve("region/r.1.0.mca")),
                Files.readAllBytes(target.resolve("region/r.1.0.mca")));
        assertEquals("new exterior chunk", Files.readString(target.resolve("region/c.33.0.mcc")),
                "external chunks accompany the full copied region, even beyond the viewing rectangle");
    }

    @Test
    void neverMergesExteriorTerrainFromAnotherCampusRevision(@TempDir Path runtime) throws IOException {
        Path source = prepareWideSource(runtime);
        Path target = runtime.resolve("private-place");
        BuildingTemplate.copy(source, target, new BuildRegion("entry", 480, -64, 0, 495, 319, 15));
        Files.writeString(source.resolve(CampusTemplateMetadata.FILE_NAME), """
                revision: replacement-campus
                block-bounds: [0, -64, 0, 1023, 319, 511]
                spawn: [0, 80, 0]
                """);

        BuildingTemplate.copyMissingTerrain(source, target,
                new BuildRegion("entry", 480, -64, 0, 527, 319, 15));

        assertFalse(Files.exists(target.resolve("region/r.1.0.mca")));
        assertFalse(Files.readString(target.resolve(CampusTemplateMetadata.FILE_NAME)).contains("replacement-campus"));
    }

    private Path prepareWideSource(Path runtime) throws IOException {
        Path source = Files.createDirectories(runtime.resolve("source"));
        Files.writeString(source.resolve(CampusTemplateMetadata.FILE_NAME), """
                block-bounds: [0, -64, 0, 1023, 319, 511]
                spawn: [0, 80, 0]
                """);
        Path regions = Files.createDirectories(source.resolve("region"));
        ByteBuffer region = ByteBuffer.allocate(12_288);
        for (int index = 0; index < 1024; index++) {
            region.putInt(index * 4, 0x00000201);
        }
        Files.write(regions.resolve("r.0.0.mca"), region.array());
        Files.write(regions.resolve("r.1.0.mca"), region.array());
        return source;
    }

    private Path prepareSource(Path runtime) throws IOException {
        Path source = Files.createDirectories(runtime.resolve("source"));
        Files.writeString(source.resolve(CampusTemplateMetadata.FILE_NAME), """
                block-bounds: [-100, -64, -100, 100, 319, 100]
                spawn: [0, 80, 0]
                """);
        Path regions = Files.createDirectories(source.resolve("region"));
        ByteBuffer region = ByteBuffer.allocate(12_288);
        region.putInt(0, 0x00000201);
        region.putInt(4, 0x00000201);
        region.putInt(128, 0x00000201);
        region.putInt(132, 0x00000201);
        Files.write(regions.resolve("r.0.0.mca"), region.array());
        return source;
    }
}
