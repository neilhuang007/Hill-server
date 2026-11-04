package org.thehill.smoke;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.google.gson.JsonDeserializer;
import com.mojang.math.Transformation;
import com.mojang.serialization.JsonOps;
import net.minecraft.client.renderer.item.CuboidItemModelWrapper;
import net.minecraft.client.renderer.item.ItemStackRenderState;
import net.minecraft.client.renderer.item.TrackingItemStackRenderState;
import net.minecraft.client.renderer.state.gui.GuiItemRenderState;
import net.minecraft.client.resources.model.cuboid.ItemTransform;
import net.minecraft.world.item.ItemDisplayContext;
import org.joml.Matrix3x2f;
import org.joml.Matrix4f;
import org.joml.Vector3f;
import org.joml.Vector3fc;

import java.nio.charset.StandardCharsets;
import java.util.zip.ZipFile;

/** Runs against the installed client classes, without starting Minecraft or opening a window. */
public final class OfficialMapDialogBounds {
    public static void main(String[] arguments) throws Exception {
        if (arguments.length != 1) throw new IllegalArgumentException("Supply the official campus pack ZIP.");
        try (var pack = new ZipFile(arguments[0])) {
            for (String name : new String[]{"official_full", "official_core"}) verify(pack, name);
        }
    }

    private static void verify(ZipFile pack, String name) throws Exception {
        JsonObject item = read(pack, "assets/hill175/items/campus/" + name + ".json");
        JsonObject model = read(pack, "assets/hill175/models/item/campus/" + name + ".json");
        var decoded = CuboidItemModelWrapper.Unbaked.MAP_CODEC.codec()
                .parse(JsonOps.INSTANCE, item.getAsJsonObject("model")).getOrThrow();
        var display = deserializeDisplay(model.getAsJsonObject("display").getAsJsonObject("gui"));
        var state = new TrackingItemStackRenderState();
        var context = ItemStackRenderState.class.getDeclaredField("displayContext");
        context.setAccessible(true);
        context.set(state, ItemDisplayContext.GUI);
        state.setOversizedInGui(item.get("oversized_in_gui").getAsBoolean());
        var layer = state.newLayer();
        layer.setItemTransform(display);
        layer.setLocalTransform(decoded.transformation().orElse(new Transformation(new Matrix4f())).getMatrix());
        layer.setExtents(() -> new Vector3fc[]{new Vector3f(0, 0, 0.46875f), new Vector3f(1, 0, 0.46875f),
                new Vector3f(1, 1, 0.53125f), new Vector3f(0, 1, 0.53125f)});
        var nativeBounds = new GuiItemRenderState(new Matrix3x2f(), state, 0, 0, null).bounds();
        String actual = "[" + nativeBounds.left() + "," + nativeBounds.top() + ","
                + nativeBounds.right() + "," + nativeBounds.bottom() + "]";
        System.out.println(name + " client rectangle " + actual + ", model AABB " + state.getModelBoundingBox());
        if (nativeBounds.left() != 0 || nativeBounds.top() != 0 || nativeBounds.right() != 256 || nativeBounds.bottom() != 256) {
            throw new AssertionError(name + " must fill [0,0,256,256], actual " + actual);
        }
    }

    @SuppressWarnings("unchecked")
    private static ItemTransform deserializeDisplay(JsonObject json) throws Exception {
        var constructor = Class.forName("net.minecraft.client.resources.model.cuboid.ItemTransform$Deserializer")
                .getDeclaredConstructor();
        constructor.setAccessible(true);
        var deserializer = (JsonDeserializer<ItemTransform>) constructor.newInstance();
        return deserializer.deserialize(json, ItemTransform.class, null);
    }

    private static JsonObject read(ZipFile pack, String path) throws Exception {
        try (var input = pack.getInputStream(pack.getEntry(path))) {
            return JsonParser.parseString(new String(input.readAllBytes(), StandardCharsets.UTF_8)).getAsJsonObject();
        }
    }
}
