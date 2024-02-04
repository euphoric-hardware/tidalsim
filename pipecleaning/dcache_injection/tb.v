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
    localparam integer dcache_data_bus_width = 8;
    localparam integer dcache_sets = 64;
    localparam integer dcache_size = 16384;
    localparam integer dcache_ways = dcache_size / (dcache_sets * dcache_block_size);
    localparam integer dcache_offset_bits = $clog2(dcache_block_size);
    localparam integer dcache_set_bits = $clog2(dcache_sets);
    localparam integer dcache_raw_tag_bits = physical_address_bits - dcache_set_bits - dcache_offset_bits;
    localparam integer dcache_tag_bits = dcache_raw_tag_bits + 2; // 2 bits for coherency metadata
    localparam integer dcache_data_rows_per_set = dcache_block_size / dcache_data_bus_width;

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

    `define DATA_ARRAY_FORCE(byte_idx) \
      bit [dcache_data_bus_width-1:0] dcache_data_array``byte_idx`` [dcache_data_rows_per_set * dcache_sets]; \
      event dcache_data_array_ready``byte_idx; \
      initial begin \
        $readmemb("data/dcache_data_array``byte_idx.bin", dcache_data_array``byte_idx``); \
        -> dcache_data_array_ready``byte_idx; \
      end \
      for (genvar row_idx=0; row_idx < dcache_data_rows_per_set * dcache_sets; row_idx++) begin \
        initial begin \
          wait(dcache_data_array_ready``byte_idx.triggered) begin end \
          force `DATA_ARRAY_ROOT.mem_0_``byte_idx.ram[row_idx] = dcache_data_array``byte_idx[row_idx]; \
          // @(negedge resetting) begin end \
          repeat (10) @(posedge clk); \
          release `DATA_ARRAY_ROOT.mem_0_``byte_idx.ram[row_idx]; \
        end \
      end \

    // There are data_bus_width * ways (8 * 4 = 32) dcache data RAMs
    `DATA_ARRAY_FORCE(0);
    `DATA_ARRAY_FORCE(1);
    `DATA_ARRAY_FORCE(2);
    `DATA_ARRAY_FORCE(3);
    `DATA_ARRAY_FORCE(4);
    `DATA_ARRAY_FORCE(5);
    `DATA_ARRAY_FORCE(6);
    `DATA_ARRAY_FORCE(7);
    `DATA_ARRAY_FORCE(8);
    `DATA_ARRAY_FORCE(9);
    `DATA_ARRAY_FORCE(10);
    `DATA_ARRAY_FORCE(11);
    `DATA_ARRAY_FORCE(12);
    `DATA_ARRAY_FORCE(13);
    `DATA_ARRAY_FORCE(14);
    `DATA_ARRAY_FORCE(15);
    `DATA_ARRAY_FORCE(16);
    `DATA_ARRAY_FORCE(17);
    `DATA_ARRAY_FORCE(18);
    `DATA_ARRAY_FORCE(19);
    `DATA_ARRAY_FORCE(20);
    `DATA_ARRAY_FORCE(21);
    `DATA_ARRAY_FORCE(22);
    `DATA_ARRAY_FORCE(23);
    `DATA_ARRAY_FORCE(24);
    `DATA_ARRAY_FORCE(25);
    `DATA_ARRAY_FORCE(26);
    `DATA_ARRAY_FORCE(27);
    `DATA_ARRAY_FORCE(28);
    `DATA_ARRAY_FORCE(29);
    `DATA_ARRAY_FORCE(30);
    `DATA_ARRAY_FORCE(31);

    initial begin
        $fsdbDumpfile("dump.fsdb");
        $fsdbDumpvars("+all");
        repeat (10) @(posedge clk);
        $finish();
    end
endmodule
