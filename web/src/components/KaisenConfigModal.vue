<template>
  <div id="kaisen-config-modal" class="modal fade" data-backdrop="static" data-keyboard="false">
    <div class="modal-dialog modal-dialog-centered modal-xl">
      <div class="modal-content" @click.stop>
        <h5 class="modal-header">凯旋杯配置</h5>
        <div class="modal-body">
          <div class="row">
            <div class="col-12">
              <h5>选择养成模式</h5>
              <div class="form-group">
                <div class="form-check mb-3 ps-0">
                  <input class="form-check-input" type="radio" id="km_normal" :value="1" v-model.number="internalKaisenMode">
                  <label class="form-check-label" for="km_normal">普通模式(本次育成为普通育成，不会挑战训练员技能考试)</label>
                </div>
                <div class="form-check mb-3 ps-0">
                  <input class="form-check-input" type="radio" id="km_challenge" :value="2" v-model.number="internalKaisenMode">
                  <label class="form-check-label" for="km_challenge">挑战训练员技能考试(可向针对适应性的各种考试发起挑战)</label>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <span class="btn auto-btn confirm-btn-large" v-on:click="confirm">确定</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'KaisenConfigModal',
  props: {
    show: Boolean,
    kaisenMode: {
      type: Number,
      default: 1
    },
  },
  emits: ['update:show', 'confirm'],
  data() {
    return {
      internalKaisenMode: this.kaisenMode,
    };
  },
  watch: {
    show(newVal) {
      if (newVal) {
        $('#kaisen-config-modal').modal({ backdrop: 'static', keyboard: false, show: true });
      } else {
        $('#kaisen-config-modal').modal('hide');
      }
    },
    kaisenMode(newVal) { this.internalKaisenMode = newVal; },
  },
  methods: {
    confirm() {
      this.$emit('confirm', { kaisenMode: Number(this.internalKaisenMode) });
      this.$emit('update:show', false);
      this.$nextTick(() => {
        this.restoreParentModalScrolling();
      });
    },
    restoreParentModalScrolling() {
      setTimeout(() => {
        if ($('.modal-open').length > 0) {
          $('body').addClass('modal-open');
          const parentModal = $('#create-task-list-modal');
          if (parentModal.hasClass('show')) {
            const modalBody = parentModal.find('.modal-body');
            if (modalBody.length > 0) {
              modalBody.css('overflow-y', 'auto');
              modalBody[0].offsetHeight;
            }
          }
        }
      }, 100);
    },
  },
  mounted() {
    $('#kaisen-config-modal').on('hidden.bs.modal', () => {
      this.$emit('update:show', false);
    });
  }
};
</script>

<style scoped>
#kaisen-config-modal.modal { z-index: 1060; }
#kaisen-config-modal .modal-dialog { z-index: 1061; }
.confirm-btn-large {
  padding: 0.5rem 1rem !important;
  font-size: 1rem !important;
  font-weight: 400 !important;
  min-width: 60px;
  min-height: 40px;
}
.form-check { display: flex; align-items: center; }
.form-check-input { margin-top: 0 !important; margin-right: 8px; flex-shrink: 0; }
.form-check-label { margin-bottom: 0; line-height: 1.4; }
</style>
