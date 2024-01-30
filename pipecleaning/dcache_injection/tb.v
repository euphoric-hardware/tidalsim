`include "tag_array.v"
`include "data_array.v"

module tb();
    reg clk = 0;
    always #1 clk <= ~clk;

    // /TestDriver/testHarness/chiptop0/system/tile_prci_domain/element_reset_domain_rockettile/dcache/tag_array
    tag_array_ext tag_array(
        .RW0_addr(6'd0),
        .RW0_clk(clk),
        .RW0_wdata(88'd0),
        .RW0_rdata(),
        .RW0_en(1'b1),
        .RW0_wmode(1'b0),
        .RW0_wmask(4'd0)
    );

    // /TestDriver/testHarness/chiptop0/system/tile_prci_domain/element_reset_domain_rockettile/dcache/data/data_arrays_0/data_arrays_0_ext
    data_arrays_0_ext data_array(
      .RW0_addr(9'd0),
      .RW0_en(1'b1),
      .RW0_clk(clk),
      .RW0_wmode(1'b0),
      .RW0_wdata(256'd0),
      .RW0_wmask(32'd0),
      .RW0_rdata()
    );

    `define TAG_ARRAY_ROOT tag_array
    `define DATA_ARRAY_ROOT data_array

    // DCache functional warmup
    localparam integer physical_address_bits = 32;
    localparam integer dcache_block_size = 64;
    localparam integer dcache_sets = 64;
    localparam integer dcache_size = 16384;
    localparam integer dcache_ways = dcache_size / (dcache_sets * dcache_block_size);
    localparam integer dcache_offset_bits = $clog2(dcache_block_size);
    localparam integer dcache_set_bits = $clog2(dcache_sets);
    localparam integer dcache_raw_tag_bits = physical_address_bits - dcache_set_bits - dcache_offset_bits;
    localparam integer dcache_tag_bits = dcache_raw_tag_bits + 2; // 2 bits for coherency metadata

    `define TAG_ARRAY_FORCE(way_idx) \
      bit [dcache_tag_bits-1:0] dcache_tag_array``way_idx`` [dcache_sets]; \
      event dcache_tag_array_ready``way_idx; \
      initial begin \
        $readmemb("data/dcache_tag_array``way_idx.bin", dcache_tag_array``way_idx``); \
        -> dcache_tag_array_ready``way_idx; \
      end \
      for (genvar set_idx=0; set_idx < dcache_sets; set_idx++) begin \
        initial begin \
          wait(dcache_tag_array_ready``way_idx.triggered) begin end \
          force `TAG_ARRAY_ROOT.mem_0_``way_idx.ram[set_idx] = dcache_tag_array``way_idx[set_idx]; \
          // @(negedge resetting) begin end \
          repeat (10) @(posedge clk); \
          release `TAG_ARRAY_ROOT.mem_0_``way_idx.ram[set_idx]; \
        end \
      end \

    // This is very stupid, there doesn't seem to be a way to do this
    // programmatically since macros are just string substitution.
    // We are forced to use macros since force statements must have fully
    // specified hierarchical paths at elaboration time.
    `TAG_ARRAY_FORCE(0);
    `TAG_ARRAY_FORCE(1);
    `TAG_ARRAY_FORCE(2);
    `TAG_ARRAY_FORCE(3);

    initial begin
        $fsdbDumpfile("dump.fsdb");
        $fsdbDumpvars("+all");
        repeat (10) @(posedge clk);
        $finish();
    end
endmodule
